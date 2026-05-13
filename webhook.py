from flask import Flask, request, jsonify
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import re

app = Flask(__name__)

CBR_DAILY_URL = "https://www.cbr.ru/scripts/XML_daily.asp"
CBR_DYNAMIC_URL = "https://www.cbr.ru/scripts/XML_dynamic.asp"

CURRENCY_NAMES = {
    "доллар": "USD",
    "доллара": "USD",
    "usd": "USD",
    "бакс": "USD",
    "бакса": "USD",

    "евро": "EUR",
    "eur": "EUR",

    "юань": "CNY",
    "юаня": "CNY",
    "cny": "CNY",

    "лира": "TRY",
    "лиры": "TRY",
    "турецкая лира": "TRY",
    "турецкой лиры": "TRY",
    "try": "TRY",

    "тенге": "KZT",
    "казахстанский тенге": "KZT",
    "казахстанского тенге": "KZT",
    "kzt": "KZT",

    "дирхам": "AED",
    "дирхама": "AED",
    "дирхам оаэ": "AED",
    "дирхам эмиратов": "AED",
    "aed": "AED",
}

VALUTE_IDS = {
    "USD": "R01235",
    "EUR": "R01239",
    "CNY": "R01375",
    "TRY": "R01700J",
    "KZT": "R01335",
    "AED": "R01230",
}


def find_currency(text: str):
    text = text.lower()
    for word, code in CURRENCY_NAMES.items():
        if word in text:
            return code
    return None

def find_amount(text: str):
    match = re.search(r"\d+(?:[.,]\d+)?", text)
    if match:
        return float(match.group().replace(",", "."))
    return None

def get_cbr_rate(currency_code: str):
    response = requests.get(CBR_DAILY_URL, timeout=10)
    response.encoding = "windows-1251"

    root = ET.fromstring(response.text)
    date = root.attrib.get("Date")

    for valute in root.findall("Valute"):
        char_code = valute.find("CharCode").text

        if char_code == currency_code:
            nominal = int(valute.find("Nominal").text)
            name = valute.find("Name").text
            value = float(valute.find("Value").text.replace(",", "."))
            rate = value / nominal
            return name, round(rate, 4), date

    return None, None, date


def get_currency_history(currency_code: str, days: int = 7):
    valute_id = VALUTE_IDS.get(currency_code)

    if not valute_id:
        return [], []

    end_date = datetime.now()
    start_date = end_date - timedelta(days=days + 3)

    url = (
        f"{CBR_DYNAMIC_URL}"
        f"?date_req1={start_date.strftime('%d/%m/%Y')}"
        f"&date_req2={end_date.strftime('%d/%m/%Y')}"
        f"&VAL_NM_RQ={valute_id}"
    )

    response = requests.get(url, timeout=10)
    response.encoding = "windows-1251"

    root = ET.fromstring(response.text)

    dates = []
    values = []

    for record in root.findall("Record"):
        date = datetime.strptime(record.attrib["Date"], "%d.%m.%Y")
        nominal = int(record.find("Nominal").text)
        value = float(record.find("Value").text.replace(",", ".")) / nominal

        dates.append(date)
        values.append(value)

    return dates[-7:], values[-7:]


def make_text_chart(dates, values):
    if not dates or not values:
        return "Не удалось получить данные для графика."

    levels = "▁▂▃▄▅▆▇█"

    min_value = min(values)
    max_value = max(values)

    if max_value == min_value:
        bars = [levels[0] for _ in values]
    else:
        bars = [
            levels[int((value - min_value) / (max_value - min_value) * (len(levels) - 1))]
            for value in values
        ]

    lines = []

    for date, value, bar in zip(dates, values, bars):
        lines.append(f"{date.strftime('%d.%m')} | {value:.2f} ₽ | {bar}")

    change = values[-1] - values[0]

    if change > 0:
        trend = f"курс вырос на {abs(change):.2f} ₽"
    elif change < 0:
        trend = f"курс упал на {abs(change):.2f} ₽"
    else:
        trend = "курс не изменился"

    return "\n".join(lines) + f"\n\nТренд за период: {trend}"


def explain_currency(currency_code: str):
    if currency_code == "USD":
        return "На доллар влияют спрос на валюту, импорт, экспорт, цены на нефть, санкции, ключевая ставка и ожидания рынка."

    if currency_code == "EUR":
        return "На евро влияют экономика Евросоюза, курс доллара, торговля с Европой и общая ситуация на валютном рынке."

    if currency_code == "CNY":
        return "На юань влияет торговля России с Китаем, импорт товаров, расчёты компаний и спрос на китайскую валюту."
    if currency_code == "TRY":
        return "На турецкую лиру влияют инфляция в Турции, политика Центрального банка Турции, туризм, экспорт и внешние инвестиции."

    if currency_code == "KZT":
        return "Тенге зависит от цен на нефть, торговли Казахстана, курса рубля, экспорта сырья и состояния экономики страны."

    if currency_code == "AED":
        return "Дирхам ОАЭ тесно связан с долларом США. На него влияют нефтяной рынок, торговля, туризм и финансовый сектор Эмиратов."

    return "На курс валюты влияют спрос и предложение, торговый баланс, инфляция, ключевая ставка и внешнеэкономическая ситуация."


@app.route("/webhook", methods=["POST"])

def webhook():

    data = request.get_json()

    text = data.get("queryResult", {}).get("queryText", "").lower()

    currency_code = find_currency(text)

    amount = find_amount(text)

    if not currency_code:

        answer = (

            "Напишите валюту: доллар, евро, юань, турецкая лира, тенге или дирхам ОАЭ."

        )

    else:

        if "график" in text or "динамика" in text or "за неделю" in text:

            dates, values = get_currency_history(currency_code, days=7)

            chart = make_text_chart(dates, values)

            answer = f"Динамика {currency_code} по ЦБ РФ за последние 7 значений:\n\n{chart}"

        elif amount:

            name, rate, date = get_cbr_rate(currency_code)

            if rate:

                result = amount * rate

                answer = (

                    f"{amount:g} {currency_code} по курсу ЦБ РФ на {date} = {result:.2f} ₽.\n\n"

                    f"Курс {name}: {rate} ₽."

                )

            else:

                answer = "Не смог найти курс этой валюты на сайте ЦБ РФ."

        else:

            name, rate, date = get_cbr_rate(currency_code)

            if rate:

                answer = (

                    f"Курс {name} по ЦБ РФ на {date}: {rate} ₽.\n\n"

                    f"{explain_currency(currency_code)}"

                )

            else:

                answer = "Не смог найти курс этой валюты на сайте ЦБ РФ."

    return jsonify({

        "fulfillmentText": answer

    })

@app.route("/", methods=["GET"])

def home():

    return "Webhook работает!"

if __name__ == "__main__":

    app.run(port=5000)
