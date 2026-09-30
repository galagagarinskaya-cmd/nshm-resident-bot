import os
import logging
from google.oauth2.service_account import Credentials
from googleapiclient import discovery
from config import SHEETS_ID
from typing import List, Dict, Optional
from database import Database

logger = logging.getLogger(__name__)

class SheetsService:
    RESIDENTS_SHEET = "Резиденты"

    # Technical key column: the Telegram user id is stamped here so a resident
    # always resolves to the same row. Referenced BY HEADER NAME, never by a
    # fixed letter — колонки в таблице двигаются, а поиск по имени заголовка нет.
    TG_ID_HEADER = "tg_id"
    # Column that holds the resident's full name.
    NAME_HEADER = "ФИО"

    # Survey answer -> sheet column, mapped BY HEADER NAME (not by letter).
    # If a column is renamed/moved/deleted, sync keeps working (missing headers
    # are skipped with a warning instead of writing into the wrong column).
    COLUMN_MAP = {
        1: {  # Блок 1: Твоё ID
            0: "ФИО",              # Как тебя зовут
            1: "День рождения",    # ДР
            2: "Телефон",          # Телефон
            3: "Ник в Telegram",   # Ник Telegram
            4: "Профиль в ВК",     # ВК
            5: "Регион",           # Регион
        },
        2: {  # Блок 2: Твой путь
            0: "Учеба",
            1: "Профессия",
            2: "Статус работы",
            3: "Место работы",
            4: "Ссылка на блог",
        },
        3: {  # Блок 3: Бэкграунд в НШМ
            0: "Участник каких меро",
            1: "Цель в комьюнити",
            2: "Амбассадор (советую проект)",
        },
        4: {  # Блок 4: Твой вайб
            0: "новости",
            1: "блогеры",
            2: "соцсети где сидит",
            3: "3 канала в ТГ, ютубе и ВК",
            4: "исполнители",
        },
        5: {  # Блок 5: Level Up
            0: "Знания, которых не хватило",
            1: "Нужная тема курса",
        },
    }

    def __init__(self, credentials_path: str = None):
        self.sheets_id = SHEETS_ID
        self.service = None
        self.db = Database()
        self.init_service(credentials_path)

    # ── helpers ──────────────────────────────────────────────────────────────
    @staticmethod
    def _col_letter(n: int) -> str:
        """1-based column index -> A1 letter (1->A, 27->AA)."""
        s = ""
        while n > 0:
            n, r = divmod(n - 1, 26)
            s = chr(65 + r) + s
        return s

    def _header_map(self) -> Dict[str, int]:
        """{header name: 1-based column index} from row 1 of the Резиденты sheet."""
        res = self.service.spreadsheets().values().get(
            spreadsheetId=self.sheets_id, range=f"{self.RESIDENTS_SHEET}!1:1"
        ).execute()
        rows = res.get("values", [])
        headers = rows[0] if rows else []
        return {str(h).strip(): i + 1 for i, h in enumerate(headers) if str(h).strip()}

    def _ensure_grid_columns(self, min_cols: int):
        """Make sure the sheet has at least `min_cols` columns (grow if needed)."""
        try:
            meta = self.service.spreadsheets().get(spreadsheetId=self.sheets_id).execute()
            for s in meta.get("sheets", []):
                p = s.get("properties", {})
                if p.get("title") == self.RESIDENTS_SHEET:
                    cc = p.get("gridProperties", {}).get("columnCount", 0)
                    if cc < min_cols:
                        self.service.spreadsheets().batchUpdate(
                            spreadsheetId=self.sheets_id,
                            body={"requests": [{"appendDimension": {
                                "sheetId": p.get("sheetId"),
                                "dimension": "COLUMNS",
                                "length": min_cols - cc,
                            }}]},
                        ).execute()
                        logger.info(f"Expanded {self.RESIDENTS_SHEET} to {min_cols} columns")
                    return
        except Exception as e:
            logger.error(f"Could not ensure grid columns: {e}")

    def _ensure_header(self, name: str, hmap: Dict[str, int] = None) -> Optional[int]:
        """Return the 1-based column index of header `name`, creating it if missing.

        Only used for the technical tg_id column, so the key column self-heals
        even if someone deletes it.
        """
        if hmap is None:
            hmap = self._header_map()
        if name in hmap:
            return hmap[name]
        col_idx = (max(hmap.values()) if hmap else 0) + 1
        self._ensure_grid_columns(col_idx)
        try:
            self.service.spreadsheets().values().update(
                spreadsheetId=self.sheets_id,
                range=f"{self.RESIDENTS_SHEET}!{self._col_letter(col_idx)}1",
                valueInputOption="RAW", body={"values": [[name]]},
            ).execute()
            logger.info(f"Created missing column '{name}' at {self._col_letter(col_idx)}")
            return col_idx
        except Exception as e:
            logger.error(f"Could not create column '{name}': {e}")
            return None

    def _write_updates(self, updates):
        """Write a batch of cell updates, self-healing on grid-limit errors."""
        if not updates:
            return
        body = {"data": updates, "valueInputOption": "RAW"}
        try:
            self.service.spreadsheets().values().batchUpdate(
                spreadsheetId=self.sheets_id, body=body
            ).execute()
        except Exception as e:
            if "grid limit" in str(e).lower() or "exceeds" in str(e).lower():
                # Grow enough to cover the widest range we tried to write, then retry.
                want = 0
                for u in updates:
                    rng = u.get("range", "")
                    letters = "".join(ch for ch in rng.split("!")[-1] if ch.isalpha())
                    if letters:
                        n = 0
                        for ch in letters:
                            n = n * 26 + (ord(ch.upper()) - 64)
                        want = max(want, n)
                logger.warning(f"Write hit grid limits — expanding to {want} cols and retrying")
                self._ensure_grid_columns(want)
                self.service.spreadsheets().values().batchUpdate(
                    spreadsheetId=self.sheets_id, body=body
                ).execute()
            else:
                raise

    def init_service(self, credentials_path: str = None):
        """Initialize Google Sheets API service"""
        try:
            # Try to load from environment variable first (Railway).
            # The service-account JSON may be stored under GOOGLE_CREDENTIALS or,
            # as on this Railway project, under GOOGLE_CREDENTIALS_PATH (which
            # despite its name holds the JSON content itself, not a file path).
            creds_json = os.getenv("GOOGLE_CREDENTIALS")
            if not creds_json:
                _maybe = os.getenv("GOOGLE_CREDENTIALS_PATH", "")
                if _maybe.strip().startswith("{"):
                    creds_json = _maybe
            if creds_json:
                import json as json_module
                creds_dict = json_module.loads(creds_json)
                creds = Credentials.from_service_account_info(
                    creds_dict,
                    scopes=['https://www.googleapis.com/auth/spreadsheets']
                )
                self.service = discovery.build('sheets', 'v4', credentials=creds)
                logger.info("Google Sheets API initialized from env variable")
                return

            # Fallback to credentials.json (local development)
            if credentials_path is None:
                cred_file = "credentials.json"
                if os.path.exists(cred_file):
                    credentials_path = cred_file

            if not credentials_path or not os.path.exists(credentials_path):
                logger.warning("Google Sheets credentials not found. Some features will be disabled.")
                return

            creds = Credentials.from_service_account_file(
                credentials_path,
                scopes=['https://www.googleapis.com/auth/spreadsheets']
            )
            self.service = discovery.build('sheets', 'v4', credentials=creds)
            logger.info("Google Sheets API initialized from credentials file")
        except Exception as e:
            logger.error(f"Error initializing Sheets service: {e}")

    def get_rules(self) -> Dict[str, Dict]:
        """Get rules blocks from 'Правила' sheet"""
        if not self.service:
            return {}
        try:
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.sheets_id,
                range="Правила!A:C"
            ).execute()
            values = result.get('values', [])
            if not values or len(values) <= 1:
                return {}
            rules = {}
            for row in values[1:]:
                if len(row) >= 3:
                    block_num = str(row[0]).strip()
                    title = str(row[1]).strip() if len(row) > 1 else ""
                    text = str(row[2]).strip() if len(row) > 2 else ""
                    if block_num and title and text:
                        rules[block_num] = {"title": title, "text": text}
            logger.info(f"Loaded {len(rules)} rule blocks")
            return rules
        except Exception as e:
            logger.error(f"Error getting rules: {e}")
            return {}

    def get_content(self) -> Dict[str, Dict]:
        """Get content (welcome messages, circles) from 'Контент' sheet"""
        if not self.service:
            return {}
        try:
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.sheets_id,
                range="Контент!A:C"
            ).execute()
            values = result.get('values', [])
            if not values or len(values) <= 1:
                return {}
            content = {}
            for row in values[1:]:
                if len(row) >= 3:
                    block = str(row[0]).strip() if len(row) > 0 else ""
                    content_id = str(row[1]).strip() if len(row) > 1 else ""
                    text = str(row[2]).strip() if len(row) > 2 else ""
                    if content_id and text:
                        content[content_id] = {"block": block, "text": text}
            logger.info(f"Loaded {len(content)} content items")
            return content
        except Exception as e:
            logger.error(f"Error getting content: {e}")
            return {}

    # ── row lookup / creation ────────────────────────────────────────────────
    def find_resident_row_by_user_id(self, user_id: int, hmap: Dict[str, int] = None) -> Optional[int]:
        """Find a resident row by the Telegram user id in the tg_id column.

        Stable key: survey answers never write to tg_id, so a resident who comes
        back later keeps filling the same row. Column found by HEADER NAME.
        """
        if not self.service:
            return None
        try:
            if hmap is None:
                hmap = self._header_map()
            col = hmap.get(self.TG_ID_HEADER)
            if not col:
                return None
            letter = self._col_letter(col)
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.sheets_id,
                range=f"{self.RESIDENTS_SHEET}!{letter}:{letter}"
            ).execute()
            target = str(user_id)
            for idx, row in enumerate(result.get('values', [])[1:], 2):
                if row and str(row[0]).strip() == target:
                    return idx
            return None
        except Exception as e:
            logger.error(f"Error finding resident by user_id: {e}")
            return None

    def find_resident_row_by_name(self, first_name: str, last_name: str, hmap: Dict[str, int] = None) -> Optional[int]:
        """Find an existing resident row by name (matches on the set of name parts)."""
        if not self.service:
            return None
        wanted = set((first_name or "").strip().lower().split())
        wanted |= set((last_name or "").strip().lower().split())
        if not wanted:
            return None
        try:
            if hmap is None:
                hmap = self._header_map()
            col = hmap.get(self.NAME_HEADER, 1)
            letter = self._col_letter(col)
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.sheets_id,
                range=f"{self.RESIDENTS_SHEET}!{letter}:{letter}"
            ).execute()
            for idx, row in enumerate(result.get('values', [])[1:], 2):
                full_name = str(row[0]).strip().lower() if row else ""
                if full_name and wanted.issubset(set(full_name.split())):
                    return idx
            return None
        except Exception as e:
            logger.error(f"Error finding resident: {e}")
            return None

    def add_resident_row(self, user_id: int, first_name: str, last_name: str, hmap: Dict[str, int] = None) -> Optional[int]:
        """Append a new resident row (name + tg_id) and return its row number."""
        if not self.service:
            return None
        try:
            if hmap is None:
                hmap = self._header_map()
            name_col = hmap.get(self.NAME_HEADER, 1)
            name_letter = self._col_letter(name_col)
            # Next empty row = one past the last non-empty name cell.
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.sheets_id,
                range=f"{self.RESIDENTS_SHEET}!{name_letter}:{name_letter}"
            ).execute()
            next_row = len(result.get('values', [])) + 1

            updates = [{
                "range": f"{self.RESIDENTS_SHEET}!{name_letter}{next_row}",
                "values": [[f"{first_name} {last_name}".strip()]],
            }]
            tg_col = self._ensure_header(self.TG_ID_HEADER, hmap)
            if tg_col:
                updates.append({
                    "range": f"{self.RESIDENTS_SHEET}!{self._col_letter(tg_col)}{next_row}",
                    "values": [[str(user_id)]],
                })
            self._write_updates(updates)
            logger.info(f"Added new resident row {next_row}: {first_name} {last_name}")
            return next_row
        except Exception as e:
            logger.error(f"Error adding resident row: {e}")
            return None

    def sync_survey_responses(self, user_id: int, responses: List[Dict]) -> bool:
        """Sync survey responses to the resident's row (columns matched by header name)."""
        if not self.service or not responses:
            return False
        try:
            user_info = self.db.get_user(user_id)
            if not user_info:
                logger.error(f"User {user_id} not found in database")
                return False

            first_name = user_info.get("first_name", "")
            last_name = user_info.get("last_name", "")

            hmap = self._header_map()
            # tg_id column must exist so the row stays findable next time.
            if self.TG_ID_HEADER not in hmap:
                self._ensure_header(self.TG_ID_HEADER, hmap)
                hmap = self._header_map()

            # Resolve the row: tg_id first (stable), then name, then create.
            row_num = self.find_resident_row_by_user_id(user_id, hmap)
            if not row_num:
                row_num = self.find_resident_row_by_name(first_name, last_name, hmap)
            if not row_num:
                row_num = self.add_resident_row(user_id, first_name, last_name, hmap)
                hmap = self._header_map()  # columns may have changed on create

            if not row_num:
                logger.error(f"Could not find or create row for {first_name} {last_name}")
                return False

            updates = []
            # Always (re)stamp tg_id on the row.
            tg_col = hmap.get(self.TG_ID_HEADER)
            if tg_col:
                updates.append({
                    "range": f"{self.RESIDENTS_SHEET}!{self._col_letter(tg_col)}{row_num}",
                    "values": [[str(user_id)]],
                })

            # Map each answer to its column BY HEADER NAME.
            for response in responses:
                block = response["block_number"]
                q_idx = response.get("question_index", 0)
                answer = response["answer"]
                header = self.COLUMN_MAP.get(block, {}).get(q_idx)
                if not header:
                    continue
                col = hmap.get(header)
                if not col:
                    logger.warning(f"Column '{header}' not found in sheet — skipping this answer")
                    continue
                updates.append({
                    "range": f"{self.RESIDENTS_SHEET}!{self._col_letter(col)}{row_num}",
                    "values": [[answer]],
                })

            if updates:
                self._write_updates(updates)
                logger.info(f"Synced {len(updates)} cells for user {user_id} (row {row_num})")
            return True
        except Exception as e:
            logger.error(f"Error syncing survey responses: {e}")
            return False
