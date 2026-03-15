import logging
from datetime import datetime
import time
import requests
import csv
import io
from bot.misc.util import CONFIG

logger = logging.getLogger(__name__)

class YandexMetrikaAPI:
    def __init__(self, counter_id, oauth_token):
        self.counter_id = counter_id
        self.oauth_token = oauth_token

    def send_offline_conversion_payment(self, client_id, datetime_obj, months_count: int, price, currency='RUB',
                                        target='BalanceTopUp'):
        url = f"https://api-metrika.yandex.net/management/v1/counter/{self.counter_id}/offline_conversions/upload?client_id_type=CLIENT_ID"

        # Преобразуем объект datetime в Unix timestamp (в секундах)
        timestamp = int(time.mktime(datetime_obj.timetuple()))

        # Формируем данные для отправки
        data = [
            [client_id, target, timestamp, months_count, price, currency]
        ]
        logger.info(f"Sent offline conversion with data {data}")

        # Генерируем CSV файл
        csv_file = io.StringIO()
        csv_writer = csv.writer(csv_file)
        csv_writer.writerow(['ClientId', 'Target', 'DateTime', 'Duration', 'Price', 'Currency'])
        csv_writer.writerows(data)
        csv_content = csv_file.getvalue()

        # Заголовки для авторизации
        headers = {
            'Authorization': f'OAuth {self.oauth_token}'
        }

        # Отправка запроса на API Яндекс.Метрики
        files = {
            'file': ('conversions.csv', csv_content)
        }

        response = requests.post(url, headers=headers, files=files)

        if response.status_code == 200:
            logger.info("Конверсия успешно отправлена!")
            upload_id = response.json().get("upload_id")  # Получаем ID загрузки
            return upload_id
        else:
            logger.error(f"Ошибка отправки данных: {response.text}")
            return None

    def send_offline_conversion_action(self, client_id, datetime_obj, target):
        url = f"https://api-metrika.yandex.net/management/v1/counter/{self.counter_id}/offline_conversions/upload?client_id_type=CLIENT_ID"

        # Преобразуем объект datetime в Unix timestamp (в секундах)
        timestamp = int(time.mktime(datetime_obj.timetuple()))

        # Формируем данные для отправки
        data = [
            [client_id, target, timestamp]
        ]
        logger.info(f"Sent offline conversion with data {data}")

        # Генерируем CSV файл
        csv_file = io.StringIO()
        csv_writer = csv.writer(csv_file)
        csv_writer.writerow(['ClientId', 'Target', 'DateTime'])
        csv_writer.writerows(data)
        csv_content = csv_file.getvalue()

        # Заголовки для авторизации
        headers = {
            'Authorization': f'OAuth {self.oauth_token}'
        }

        # Отправка запроса на API Яндекс.Метрики
        files = {
            'file': ('conversions.csv', csv_content)
        }

        response = requests.post(url, headers=headers, files=files)

        if response.status_code == 200:
            logger.info("Конверсия успешно отправлена!")
            upload_id = response.json().get("upload_id")  # Получаем ID загрузки
            return upload_id
        else:
            logger.error(f"Ошибка отправки данных: {response.text}")
            return None

    def check_conversion_status(self, upload_id):
        url = f"https://api-metrika.yandex.net/management/v1/counter/{self.counter_id}/offline_conversions/upload/{upload_id}/status"

        # Заголовки для авторизации
        headers = {
            'Authorization': f'OAuth {self.oauth_token}'
        }

        response = requests.get(url, headers=headers)

        if response.status_code == 200:
            status = response.json()
            print("Статус загрузки:", status)
            return status
        else:
            print(f"Ошибка при проверке статуса загрузки: {response.text}")
            return None


if __name__ == "__main__":
    # Пример использования
    ym_api = YandexMetrikaAPI(counter_id=CONFIG.ym_counter, oauth_token=CONFIG.ym_oauth_token)
    client_id = '1234567890'
    target = 'TEST'
    current_time = datetime.now().astimezone()  # Получаем текущее время с учётом временной зоны
    price = 1.00
    currency = 'RUB'

    # Отправка офлайн-конверсии
    upload_id = ym_api.send_offline_conversion_payment(client_id, current_time, price, currency, target)

    # Проверка статуса загрузки (если загрузка прошла успешно)
    if upload_id:
        ym_api.check_conversion_status(upload_id)
