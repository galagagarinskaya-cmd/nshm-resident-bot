import os
import logging
from google.oauth2.service_account import Credentials
from googleapiclient import discovery
from config import SHEETS_ID
from typing import List, Dict, Optional
from database import Database

logger = logging.getLogger(__name__)

class SheetsService:
    # Columns needed on the Резиденты sheet. AA holds the tg_id technical key,
    # so the grid must have at least 27 columns or writes fail with
    # "exceeds grid limits" and the whole sync silently breaks.
    MIN_COLUMNS = 28
    RESIDENTS_SHEET = "Резиденты"

    def __init__(self, credentials_path: str = None):
        self.sheets_id = SHEETS_ID
        self.service = None
        self.db = Database()
        self._columns_ensured = False
        self.init_service(credentials_path)

    def _ensure_grid_columns(self):
        """Make sure the Резиденты sheet is wide enough (>= MIN_COLUMNS).

        Self-healing: if the sheet ever has too few columns (which is what broke
        sync when the tg_id key column AA did not exist), expand it automatically.
        Cached so the metadata call runs at most once per process.
        """
        if not self.service or self._columns_ensured:
            return
        try:
            meta = self.service.spreadsheets().get(spreadsheetId=self.sheets_id).execute()
            for s in meta.get("sheets", []):
                p = s.get("properties", {})
                if p.get("title") == self.RESIDENTS_SHEET:
                    cc = p.get("gridProperties", {}).get("columnCount", 0)
                    if cc < self.MIN_COLUMNS:
                        self.service.spreadsheets().batchUpdate(
                            spreadsheetId=self.sheets_id,
                            body={"requests": [{"appendDimension": {
                                "sheetId": p.get("sheetId"),
                                "dimension": "COLUMNS",
                                "length": self.MIN_COLUMNS - cc,
                            }}]},
                        ).execute()
                        logger.info(f"Expanded {self.RESIDENTS_SHEET} sheet to {self.MIN_COLUMNS} columns")
                    self._columns_ensured = True
                    return
        except Exception as e:
            logger.error(f"Could not ensure grid columns: {e}")

    def _write_updates(self, updates):
        """Write a batch of cell updates, self-healing on grid-limit errors."""
        body = {"data": updates, "valueInputOption": "RAW"}
        try:
            self.service.spreadsheets().values().batchUpdate(
                spreadsheetId=self.sheets_id, body=body
            ).execute()
        except Exception as e:
            # A too-small grid raises "exceeds grid limits" — expand and retry once.
            if "grid limit" in str(e).lower() or "exceeds" in str(e).lower():
                logger.warning("Write hit grid limits — expanding sheet and retrying")
                self._columns_ensured = False
                self._ensure_grid_columns()
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

    def find_resident_row_by_user_id(self, user_id: int) -> Optional[int]:
        """Find a resident row by the Telegram user id stamped in column AA.

        This is the stable key: survey answers never write to AA, so a resident
        who stops mid-survey and comes back later keeps filling the same row.
        """
        if not self.service:
            return None

        try:
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.sheets_id,
                range="Резиденты!AA:AA"
            ).execute()

            target = str(user_id)
            for idx, row in enumerate(result.get('values', [])[1:], 2):
                if row and str(row[0]).strip() == target:
                    return idx

            return None
        except Exception as e:
            logger.error(f"Error finding resident by user_id: {e}")
            return None

    def find_resident_row_by_name(self, first_name: str, last_name: str) -> Optional[int]:
        """Find an existing resident row by name.

        Column A holds "Имя + фамилия", so match on the set of name parts rather
        than on exact cell equality (the order differs between the sheet and
        Telegram profiles).
        """
        if not self.service:
            return None

        wanted = set((first_name or "").strip().lower().split())
        wanted |= set((last_name or "").strip().lower().split())
        if not wanted:
            return None

        try:
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.sheets_id,
                range="Резиденты!A:A"
            ).execute()

            for idx, row in enumerate(result.get('values', [])[1:], 2):
                full_name = str(row[0]).strip().lower() if row else ""
                if full_name and wanted.issubset(set(full_name.split())):
                    return idx

            return None
        except Exception as e:
            logger.error(f"Error finding resident: {e}")
            return None

    def add_resident_row(self, first_name: str, last_name: str) -> Optional[int]:
        """Add new resident row and return row number"""
        if not self.service:
            return None

        try:
            # Get current data to find next empty row
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.sheets_id,
                range="Резиденты!A:A"
            ).execute()

            values = result.get('values', [])
            next_row = len(values) + 1

            # Column A is "Имя + фамилия", B is "Только фамилия". Leave C alone —
            # that is "Регион" and the survey fills it in.
            row_data = [f"{first_name} {last_name}".strip(), last_name]

            # Insert the row
            self.service.spreadsheets().values().update(
                spreadsheetId=self.sheets_id,
                range=f"Резиденты!A{next_row}:B{next_row}",
                valueInputOption="RAW",
                body={"values": [row_data]}
            ).execute()

            logger.info(f"Added new resident row {next_row}: {first_name} {last_name}")
            return next_row
        except Exception as e:
            logger.error(f"Error adding resident row: {e}")
            return None

    def sync_survey_responses(self, user_id: int, responses: List[Dict]) -> bool:
        """Sync survey responses to resident row"""
        if not self.service or not responses:
            return False

        try:
            user_info = self.db.get_user(user_id)
            if not user_info:
                logger.error(f"User {user_id} not found in database")
                return False

            first_name = user_info.get("first_name", "")
            last_name = user_info.get("last_name", "")

            # Find or create the resident row. The user id in column AA is the
            # stable key, so a resident who returns to finish the survey later
            # keeps writing into the same row even after their answers have
            # overwritten the name columns.
            # Make sure the grid is wide enough before we touch column AA.
            self._ensure_grid_columns()

            row_num = self.find_resident_row_by_user_id(user_id)
            if not row_num:
                row_num = self.find_resident_row_by_name(first_name, last_name)
            if not row_num:
                row_num = self.add_resident_row(first_name, last_name)

            if not row_num:
                logger.error(f"Could not find or create row for {first_name} {last_name}")
                return False

            # Map survey responses to columns (по структуре таблицы)
            column_map = {
                1: {  # Блок 1: Твоё ID (6 вопросов)
                    0: "A",  # Q1: Как тебя зовут → Имя
                    1: "H",  # Q2: Когда ДР → День рождения
                    2: "I",  # Q3: Телефон → Телефон
                    3: "E",  # Q4: Ник Telegram → Ник в Telegram
                    4: "D",  # Q5: ВК профиль → Профиль в ВК
                    5: "C"   # Q6: Регион → Регион
                },
                2: {  # Блок 2: Твой путь (5 вопросов)
                    0: "J",  # Q1: Учеба → Учеба
                    1: "K",  # Q2: Профессия → Профессия
                    2: "L",  # Q3: Работаешь ли → Статус работы
                    3: "M",  # Q4: Где работает → Место работы
                    4: "N"   # Q5: Блог → Ссылка на блог
                },
                3: {  # Блок 3: Бэкграунд в НШМ (3 вопроса)
                    0: "F",  # Q1: Марафоны → Участник каких меро
                    1: "P",  # Q2: Цель → Цель в комьюнити
                    2: "Q"   # Q3: Амбассадор (0-10) → Амбассадор
                },
                4: {  # Блок 4: Твой вайб (5 вопросов)
                    0: "X",  # Q1: Новости
                    1: "Y",  # Q2: Блогеры
                    2: "Z",  # Q3: Соцсети
                    3: "T",  # Q4: Топ-3 TG/YouTube/ВК каналов
                    4: "W"   # Q5: Исполнители (что слушаешь)
                },
                5: {  # Блок 5: Level Up (2 вопроса)
                    0: "R",  # Q1: Знания → Знания, которых не хватило
                    1: "S"   # Q2: Курс → Нужная тема курса
                }
            }

            # Collect updates
            updates = []

            # Stamp the Telegram user id so every later answer resolves to this
            # exact row. Name columns are left to the survey answers themselves.
            updates.append({
                "range": f"Резиденты!AA{row_num}",
                "values": [[str(user_id)]]
            })

            # Add survey responses
            for response in responses:
                block = response["block_number"]
                q_idx = response.get("question_index", 0)
                answer = response["answer"]

                if block in column_map and q_idx in column_map[block]:
                    col = column_map[block][q_idx]
                    cell_range = f"Резиденты!{col}{row_num}"
                    updates.append({
                        "range": cell_range,
                        "values": [[answer]]
                    })

            # Execute batch update (self-healing on grid-limit errors)
            if updates:
                self._write_updates(updates)
                logger.info(f"Synced {len(updates)} responses for user {user_id} (row {row_num})")
                return True

            return True
        except Exception as e:
            logger.error(f"Error syncing survey responses: {e}")
            return False
