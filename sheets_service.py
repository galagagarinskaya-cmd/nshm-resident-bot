import os
import logging
from google.oauth2.service_account import Credentials
from googleapiclient import discovery
from config import SHEETS_ID
from typing import List, Dict, Optional
from database import Database

logger = logging.getLogger(__name__)

class SheetsService:
    def __init__(self, credentials_path: str = None):
        self.sheets_id = SHEETS_ID
        self.service = None
        self.db = Database()
        self.init_service(credentials_path)

    def init_service(self, credentials_path: str = None):
        """Initialize Google Sheets API service"""
        try:
            # Try to load from environment variable first (Railway)
            creds_json = os.getenv("GOOGLE_CREDENTIALS")
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

    def find_resident_row_by_name(self, first_name: str, last_name: str) -> Optional[int]:
        """Find resident row by first and last name"""
        if not self.service:
            return None

        try:
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.sheets_id,
                range="Резиденты!A:C"
            ).execute()

            values = result.get('values', [])
            if not values:
                return None

            for idx, row in enumerate(values[1:], 2):  # Start from row 2 (skip header)
                if len(row) >= 3:
                    sheet_first = str(row[1]).strip().lower() if len(row) > 1 else ""
                    sheet_last = str(row[2]).strip().lower() if len(row) > 2 else ""
                    if sheet_first == first_name.lower() and sheet_last == last_name.lower():
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

            # Prepare row data - добавим имя и фамилию
            row_data = ["", first_name, last_name]  # A (ID), B (Имя), C (Фамилия)

            # Insert the row
            self.service.spreadsheets().values().update(
                spreadsheetId=self.sheets_id,
                range=f"Резиденты!A{next_row}:C{next_row}",
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

            # Find or create resident row
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
                4: {  # Блок 4: Твой вайб (7 вопросов)
                    0: "X",  # Q1: Новости → новости где сидит
                    1: "Y",  # Q2: Блогеры → блогеры
                    2: "Z",  # Q3: Соцсети → соцсети где сидит
                    3: "T",  # Q4: ТГ-каналы → 3 ТГ-канала
                    4: "U",  # Q5: YouTube → 3 ютуб-канала
                    5: "V",  # Q6: ВК группы → группы в VK
                    6: "W"   # Q7: Исполнители → исполните ли
                },
                5: {  # Блок 5: Level Up (2 вопроса)
                    0: "R",  # Q1: Знания → Знания, которых не хватило
                    1: "S"   # Q2: Курс → Нужная тема курса
                }
            }

            # Collect updates
            updates = []

            # Add first name and last name
            updates.append({
                "range": f"Резиденты!A{row_num}",
                "values": [[first_name]]
            })
            updates.append({
                "range": f"Резиденты!B{row_num}",
                "values": [[last_name]]
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

            # Execute batch update
            if updates:
                body = {
                    "data": updates,
                    "valueInputOption": "RAW"
                }
                self.service.spreadsheets().values().batchUpdate(
                    spreadsheetId=self.sheets_id,
                    body=body
                ).execute()
                logger.info(f"Synced {len(updates)} responses for user {user_id} (row {row_num})")
                return True

            return True
        except Exception as e:
            logger.error(f"Error syncing survey responses: {e}")
            return False
