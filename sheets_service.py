import os
import json
from google.auth.transport.requests import Request
from google.oauth2.service_account import Credentials
from google.api_python_client import discovery
from config import SHEETS_ID
from typing import List, Dict

class SheetsService:
    def __init__(self, credentials_path: str = None):
        self.sheets_id = SHEETS_ID
        self.service = None
        self.init_service(credentials_path)

    def init_service(self, credentials_path: str = None):
        """Initialize Google Sheets API service"""
        if credentials_path is None:
            # Если файл не существует, создаём из JSON строки из Downloads
            cred_file = "/Users/gala/Downloads/nshm-residents-debd808b5d67.json"
            if os.path.exists(cred_file):
                credentials_path = cred_file

        if not credentials_path or not os.path.exists(credentials_path):
            print("WARNING: Google Sheets credentials not found. Some features will be disabled.")
            return

        try:
            creds = Credentials.from_service_account_file(
                credentials_path,
                scopes=['https://www.googleapis.com/auth/spreadsheets']
            )
            self.service = discovery.build('sheets', 'v4', credentials=creds)
        except Exception as e:
            print(f"Error initializing Sheets service: {e}")

    def get_rules(self) -> Dict[str, str]:
        """Get rules blocks from 'Правила' sheet"""
        if not self.service:
            return {}

        try:
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.sheets_id,
                range="Правила!A:C"
            ).execute()

            values = result.get('values', [])
            if not values:
                return {}

            rules = {}
            for row in values[1:]:  # Skip header
                if len(row) >= 3:
                    block_num = row[0]
                    title = row[1]
                    text = row[2]
                    rules[block_num] = {"title": title, "text": text}

            return rules
        except Exception as e:
            print(f"Error getting rules: {e}")
            return {}

    def get_content(self) -> Dict[str, str]:
        """Get content (welcome messages, circles, etc) from 'Контент' sheet"""
        if not self.service:
            return {}

        try:
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.sheets_id,
                range="Контент!A:C"
            ).execute()

            values = result.get('values', [])
            if not values:
                return {}

            content = {}
            for row in values[1:]:  # Skip header
                if len(row) >= 3:
                    block = row[0]
                    content_id = row[1]
                    text = row[2]
                    content[content_id] = {"block": block, "text": text}

            return content
        except Exception as e:
            print(f"Error getting content: {e}")
            return {}

    def get_survey_questions(self) -> Dict[int, List[Dict]]:
        """Get survey questions from 'Опрос' sheet"""
        if not self.service:
            return {}

        try:
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.sheets_id,
                range="Опрос!A:C"
            ).execute()

            values = result.get('values', [])
            if not values:
                return {}

            questions = {}
            for row in values[1:]:  # Skip header
                if len(row) >= 3:
                    block_num = int(row[0])
                    question = row[1]
                    question_type = row[2]  # text, choice, etc

                    if block_num not in questions:
                        questions[block_num] = []

                    questions[block_num].append({
                        "question": question,
                        "type": question_type
                    })

            return questions
        except Exception as e:
            print(f"Error getting survey questions: {e}")
            return {}

    def update_resident(self, row_number: int, data: Dict[str, str]):
        """Update resident data in main sheet"""
        if not self.service:
            return

        try:
            # Map data to columns
            columns = {
                "name": "B",
                "last_name": "C",
                "region": "D",
                "vk_profile": "E",
                "telegram_nick": "F",
                "participated_events": "G",
                "activity": "H",
                "birthday": "I",
                "phone": "J",
                "education": "K",
                "profession": "L",
                "work_status": "M",
                "workplace": "N",
                "blog_link": "O",
                "participation_history": "P",
                "community_goal": "Q",
                "ambassador": "R",
                "missing_knowledge": "S",
                "needed_course": "T",
                "tg_channels": "U",
                "youtube_channels": "V",
                "vk_communities": "W",
                "artists": "X",
                "news_sources": "Y",
                "bloggers": "Z",
                "social_networks": "AA"
            }

            updates = []
            for key, col in columns.items():
                if key in data:
                    cell_range = f"Резиденты!{col}{row_number}"
                    updates.append({
                        "range": cell_range,
                        "values": [[data[key]]]
                    })

            if updates:
                body = {"data": updates}
                self.service.spreadsheets().values().batchUpdate(
                    spreadsheetId=self.sheets_id,
                    body=body
                ).execute()
        except Exception as e:
            print(f"Error updating resident: {e}")

    def find_resident_row(self, full_name: str) -> int:
        """Find resident row by full name"""
        if not self.service:
            return -1

        try:
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.sheets_id,
                range="Резиденты!B:C"
            ).execute()

            values = result.get('values', [])
            for idx, row in enumerate(values, 1):
                if len(row) >= 2:
                    name_cell = f"{row[0]} {row[1]}"
                    if name_cell.lower() == full_name.lower():
                        return idx + 1  # +1 for 1-indexing and header

            return -1
        except Exception as e:
            print(f"Error finding resident: {e}")
            return -1

    def add_new_resident(self, data: Dict[str, str]):
        """Add new resident to sheet"""
        if not self.service:
            return

        try:
            # Get the next empty row
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.sheets_id,
                range="Резиденты!A:A"
            ).execute()

            values = result.get('values', [])
            next_row = len(values) + 1

            # Prepare data for all columns
            row_data = [""] * 27  # A to AA
            row_data[1] = data.get("name", "")  # B
            row_data[2] = data.get("last_name", "")  # C
            # ... more mappings

            self.service.spreadsheets().values().update(
                spreadsheetId=self.sheets_id,
                range=f"Резиденты!A{next_row}:AA{next_row}",
                valueInputOption="RAW",
                body={"values": [row_data]}
            ).execute()
        except Exception as e:
            print(f"Error adding resident: {e}")

    def sync_survey_response(self, user_id: int, responses: list):
        """Sync survey responses to sheets"""
        if not self.service:
            return

        try:
            # Map survey blocks to column names
            column_map = {
                1: {  # Блок ID
                    0: "B",  # Имя
                    1: "I",  # День рождения
                    2: "J",  # Телефон
                    3: "F",  # Ник в Telegram
                    4: "E",  # Профиль в ВК
                    5: "D"   # Регион
                },
                2: {  # Блок Учеба и работа
                    0: "K",  # Образование
                    1: "L",  # Профессия
                    2: "M",  # Статус работы
                    3: "N",  # Место работы
                    4: "O"   # Ссылка на блог
                },
                3: {  # Блок НШМ
                    0: "G",  # Участник каких меро
                    1: "Q",  # Цель в комьюнити
                    2: "R"   # Амбассадор (советую проект)
                },
                4: {  # Блок Вайб
                    0: "Y",  # Новости
                    1: "Z",  # Блогеры
                    2: "AA", # Соцсети
                    3: "U",  # 3 ТГ-канала
                    4: "V",  # 3 ютуб-канала
                    5: "W",  # Группы в VK
                    6: "X"   # Исполнители
                },
                5: {  # Блок Level Up
                    0: "S",  # Знания, которых не хватило
                    1: "T"   # Нужная тема курса
                }
            }

            updates = []
            for response in responses:
                block = response["block_number"]
                answer = response["answer"]

                if block in column_map:
                    # Find row for this user (by ФИО or other identifier)
                    # For now, we'll just add the update
                    # In production, you'd need to find the actual row number
                    pass

            # Execute batch update if there are updates
            if updates:
                body = {"data": updates}
                self.service.spreadsheets().values().batchUpdate(
                    spreadsheetId=self.sheets_id,
                    body=body
                ).execute()
                print(f"Synced {len(updates)} responses for user {user_id}")

        except Exception as e:
            print(f"Error syncing survey response: {e}")
