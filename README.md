# Jira Autocompleter

Локальный Telegram-бот, который превращает короткое описание в подробную задачу на
русском языке. Перед каждым запросом бот обновляет публичный GitHub-репозиторий
пользователя, читает tracked-документацию и исходный код, а затем вызывает
`gpt-5.3-codex` через OpenAI Responses API.

Если информации не хватает, бот задаёт одним списком до пяти вопросов. После одного
сообщения с ответами он формирует итоговую постановку и отдельно показывает открытые
вопросы. История готовых задач не сохраняется.

Сообщение `Никита` запускает отдельный сценарий: Codex придумывает комплимент, локальный
TeraTTS озвучивает его, а бот отправляет только Telegram voice.

Подробные требования находятся в [PRD.md](PRD.md).

## Возможности MVP

- доступ по списку Telegram username из `whitelist.txt`;
- индивидуальный публичный GitHub-репозиторий через `/repo <url>`;
- сохранение настройки репозитория в SQLite;
- обновление ветки `dev` перед каждой задачей с fallback на default branch;
- чтение всего tracked-текстового содержимого небольшого репозитория;
- один список максимум из пяти уточняющих вопросов;
- готовая задача в Telegram, длинный текст разбивается на несколько сообщений;
- локальный TeraTTS через HTTP;
- `/cancel` для сброса активного черновика.

## Безопасность

Репозиторий публичный. Никогда не добавляйте токены в исходники, PRD, README или
сообщения коммитов. Хук `.githooks/pre-commit` блокирует распространённые форматы ключей.

Если Telegram-токен был опубликован в чате или логе, сначала отзовите его через
BotFather командой `/revoke`, затем создайте новый. Скомпрометированный токен нельзя
считать безопасным даже после удаления сообщения.

Бот читает только файлы из `git ls-files`, пропускает бинарные файлы и denylist секретных
имён (`.env`, ключи, credentials). Код из анализируемого репозитория не выполняется.

## Установка на ноутбуке

Требуется Python 3.9+ и Git.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Заполните в `.env` как минимум:

```dotenv
TELEGRAM_BOT_TOKEN=новый_токен_из_BotFather
OPENAI_API_KEY=ключ_OpenAI_API
```

Модель по умолчанию — `gpt-5.3-codex`. Для `@nafanyah` автоматически задаётся
`https://github.com/mlops-summer-day-2026/team-02`. Разрешённые пользователи перечислены
в `whitelist.txt`, по одному username на строку.

## Локальный TeraTTS

Установка TeraTTS находится в `/Users/razraz/Documents/TeraTTS`. В ней есть CLI,
но нет HTTP-сервера, поэтому проект содержит локальный wrapper, который держит модель
в памяти и конвертирует WAV в M4A системной утилитой macOS `afconvert`.

Запуск сервиса:

```bash
/Users/razraz/Documents/TeraTTS/.venv/bin/python \
  scripts/teratts_server.py \
  --teratts-home /Users/razraz/Documents/TeraTTS \
  --preload
```

Проверка:

```bash
curl http://127.0.0.1:8001/health
```

HTTP-контракт:

```http
POST http://127.0.0.1:8001/synthesize
Content-Type: application/json
Accept: audio/ogg, audio/mp4, audio/mpeg

{"text":"Никита, ...","response_format":"telegram_voice"}
```

Успешный ответ содержит OGG/Opus, M4A или MP3. Все три формата поддерживаются Telegram
voice. Если используется другой TeraTTS-сервис, достаточно изменить адаптер
`jira_autocompleter/tts.py` и `TERATTS_URL` в `.env`.

## Запуск

```bash
source .venv/bin/activate
python -m jira_autocompleter
```

Бот работает через long polling и должен оставаться запущенным на ноутбуке.

## Использование

```text
/start
/repo https://github.com/owner/repository
/cancel
```

После настройки репозитория отправьте обычным сообщением короткое описание задачи.
Ответ на вопросы также отправляется одним сообщением.

## Тесты

```bash
source .venv/bin/activate
python -m unittest discover -s tests -v
```

Тесты не обращаются к Telegram, OpenAI или TeraTTS: внешние HTTP-вызовы подменены mock.

## Структура

```text
jira_autocompleter/
  __main__.py       запуск long polling
  config.py         переменные окружения
  telegram_app.py   команды и состояния диалога
  storage.py        SQLite-настройки и активные черновики
  repository.py     GitHub URL, обновление ветки и безопасное чтение файлов
  llm.py            OpenAI Responses API и Structured Outputs
  tts.py            HTTP-адаптер TeraTTS
  text.py           разбиение длинных Telegram-сообщений
tests/              unit-тесты
scripts/teratts_server.py  локальный HTTP-wrapper TeraTTS
```

## За рамками MVP

- создание задач в Jira;
- приватные GitHub-репозитории;
- история готовых задач;
- несколько репозиториев на пользователя;
- повторное редактирование уже сформированной задачи.
