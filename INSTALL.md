# Инструкция по установке и инициализации backup_shares

## 1. Системные требования

- **ОС:** Windows 7 SP1 (с обновлением TLS 1.2 — KB3140245)
- **Права:** Администратор (обязательно для VSS и сохранения ACL)
- **Диск:** NTFS (для сохранения атрибутов и прав доступа)
- **Свободное место:** минимум 2× от объема бэкапируемых данных + 10%
- **Сетевой доступ:** к целевым SMB-шарам

---

## 2. Установка Python 3.8.10

> Python 3.8.10 — последняя версия, официально поддерживающая Windows 7.

1. Скачайте установщик: https://www.python.org/ftp/python/3.8.10/python-3.8.10-amd64.exe
2. Запустите установщик **от имени Администратора**.
3. Обязательно отметьте:
   - ✅ `Add Python 3.8 to PATH`
   - ✅ `Install pip`
   - Выберите `Customize installation` → на последнем шаге ✅ `Install for all users`
4. Установите **Microsoft Visual C++ Redistributable 2015-2022** (нужен для pywin32 и cryptography):
   - https://aka.ms/vs/17/release/vc_redist.x64.exe

### Проверка
Откройте `cmd` и выполните:
```cmd
python --version
pip --version
```
Ожидаемый вывод: `Python 3.8.10`

---

## 3. Настройка pip для Windows 7

Windows 7 по умолчанию использует TLS 1.0/1.1, которые PyPI больше не поддерживает. Нужно принудительно включить TLS 1.2.

Создайте файл `%APPDATA%\pip\pip.ini` со следующим содержимым:
```ini
[global]
trusted-host = pypi.org
               pypi.python.org
               files.pythonhosted.org
```

Если после установки KB3140245 и перезагрузки pip всё равно выдаёт ошибку `SSL: TLSV1_ALERT_PROTOCOL_VERSION`, используйте флаг:
```cmd
pip install --trusted-host pypi.org --trusted-host files.pythonhosted.com <package>
```

---

## 4. Установка pipenv

```cmd
pip install --upgrade pip
pip install pipenv==2023.12.1
```

> Версия pipenv зафиксирована, так как более новые версии могут требовать Python ≥ 3.9.

Проверка:
```cmd
pipenv --version
```

---

## 5. Создание структуры проекта

Создайте корневую папку проекта, например `C:\share_backups\`:

```cmd
mkdir C:\share_backups
cd C:\share_backups
```

Создайте структуру каталогов согласно п. 11 ТЗ:
```cmd
mkdir auth config db backup restore ui scheduler
type nul > main.py
type nul > auth\__init__.py
type nul > auth\credentials.py
type nul > auth\password_dialog.py
type nul > config\__init__.py
type nul > config\ini_handler.py
type nul > config\cron_parser.py
type nul > db\__init__.py
type nul > db\schema.sql
type nul > db\db_manager.py
type nul > db\temp_table.py
type nul > backup\__init__.py
type nul > backup\full_backup.py
type nul > backup\incremental_backup.py
type nul > backup\robocopy_runner.py
type nul > backup\vss_manager.py
type nul > backup\verifier.py
type nul > restore\__init__.py
type nul > restore\restore_dialog.py
type nul > ui\__init__.py
type nul > ui\main_window.py
type nul > ui\tray.py
type nul > ui\status_indicator.py
type nul > ui\config_editor.py
type nul > scheduler\__init__.py
type nul > scheduler\scheduler.py
```

---

## 6. Создание Pipfile

В корне проекта создайте файл `Pipfile` со следующим содержимым:

```toml
[[source]]
url = "https://pypi.org/simple"
verify_ssl = true
name = "pypi"

[packages]
croniter = "==1.4.1"
pystray = "==0.19.5"
Pillow = "==10.0.1"
pywin32 = "==306"
cryptography = "==41.0.7"

[dev-packages]
pyinstaller = "==5.13.2"

[requires]
python_version = "3.8"
```

### Пояснение зависимостей:
| Пакет | Назначение |
|---|---|
| `croniter` | Парсинг cron-выражений (п. 2.1.2) |
| `pystray` + `Pillow` | Сворачивание в трей и иконка (п. 4) |
| `pywin32` | VSS через WMI, проверка прав администратора через `win32security` (п. 6.1, 6.3) |
| `cryptography` | PBKDF2 + AES для шифрования мастер-пароля и паролей шар (п. 1.1, 1.2) |
| `pyinstaller` (dev) | Сборка в .exe для распространения |

> `tkinter` и `sqlite3` входят в стандартную библиотеку Python и не требуют установки.
> `robocopy` — системная утилита Windows, находится в `C:\Windows\System32\robocopy.exe`.

---

## 7. Создание виртуального окружения

Выполните в корне проекта:

```cmd
pipenv install
```

pipenv:
- создаст виртуальное окружение Python 3.8
- установит все зависимости
- сгенерирует `Pipfile.lock` с зафиксированными версиями

Проверка:
```cmd
pipenv run python -c "import croniter, pystray, win32security, cryptography; print('OK')"
```

Должно вывести `OK`.

---

## 8. Инициализация базы данных

Создайте файл `db\schema.sql` со следующим содержимым:

```sql
-- Таблица журнала бэкапов
CREATE TABLE IF NOT EXISTS backup_log (
    backup_id INTEGER PRIMARY KEY AUTOINCREMENT,
    backup_type TEXT NOT NULL CHECK(backup_type IN ('full','incremental')),
    cron_id INTEGER,
    start_time TEXT NOT NULL,
    end_time TEXT,
    status TEXT NOT NULL CHECK(status IN ('running','success','error','cancelled','no_space','skipped'))
);

-- Таблица сохранённых файлов
CREATE TABLE IF NOT EXISTS backuped_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    backup_id INTEGER NOT NULL,
    cron_id INTEGER,
    backup_type TEXT NOT NULL CHECK(backup_type IN ('full','incremental')),
    share_nic TEXT NOT NULL,
    share_name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    file_size INTEGER NOT NULL,
    file_attributes TEXT,
    file_permissions TEXT,
    created_time TEXT,
    modified_time TEXT,
    backup_timestamp TEXT NOT NULL,
    FOREIGN KEY (backup_id) REFERENCES backup_log(backup_id)
);

CREATE INDEX IF NOT EXISTS idx_backuped_files_backup_id ON backuped_files(backup_id);
CREATE INDEX IF NOT EXISTS idx_backuped_files_share_path ON backuped_files(share_nic, file_path);
CREATE INDEX IF NOT EXISTS idx_backuped_files_timestamp ON backuped_files(backup_timestamp);

-- Таблица удалённых файлов
CREATE TABLE IF NOT EXISTS deleted_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    backup_id INTEGER NOT NULL,
    full_backup_id INTEGER,
    cron_id INTEGER,
    share_nic TEXT NOT NULL,
    share_name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    deletion_timestamp TEXT NOT NULL,
    FOREIGN KEY (backup_id) REFERENCES backup_log(backup_id)
);

CREATE INDEX IF NOT EXISTS idx_deleted_files_timestamp ON deleted_files(deletion_timestamp);

-- Текущее состояние программы (одна строка)
CREATE TABLE IF NOT EXISTS current_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    status TEXT NOT NULL CHECK(status IN ('idle','running','error','no_space')),
    current_cron_id INTEGER,
    current_backup_id INTEGER,
    current_backup_timestamp TEXT,
    current_backup_type TEXT,
    last_success_cron_id INTEGER,
    last_success_backup_id INTEGER,
    last_success_backup_timestamp TEXT,
    last_success_backup_type TEXT,
    last_processed_cron_time TEXT
);

INSERT OR IGNORE INTO current_state (id, status) VALUES (1, 'idle');

-- Кулдаун ошибок
CREATE TABLE IF NOT EXISTS error_cooldown (
    cron_id INTEGER PRIMARY KEY,
    last_error_time TEXT NOT NULL,
    error_count INTEGER NOT NULL DEFAULT 0
);

-- Актуальное состояние файлов на шарах
CREATE TABLE IF NOT EXISTS current_file_state (
    share_nic TEXT NOT NULL,
    file_path TEXT NOT NULL,
    last_backup_id INTEGER,
    file_size INTEGER NOT NULL,
    modified_time TEXT,
    attributes_hash TEXT,
    PRIMARY KEY (share_nic, file_path)
);

-- Временные таблицы создаются динамически в коде (с префиксом temp_)
```

Инициализация БД (выполняется один раз при первом запуске программы через `db_manager.py`):

```python
# Пример вызова в db/db_manager.py
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "share_backups.db"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"

def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.commit()
    conn.close()
```

---

## 9. Создание файла конфигурации

Создайте файл `config\settings.ini` (будет перезаписан из интерфейса):

```ini
[General]
target_backup_path = D:\Backups
cooldown_minutes = 60
run_overdue = 0

[CronProfiles]
# Формат: profile_<id> = <backup_type>|<cron_expression>
profile_1 = full|0 2 * * 0
profile_2 = incremental|0 2 * * 1-6

[Shares]
# Формат: <share_nic> = <share_name>|<login_enc>|<password_enc>|<mt_threads>
# Пароли шифруются при сохранении через credentials.py
```

---

## 10. Первый запуск и инициализация мастер-пароля

### 10.1. Запуск от имени Администратора

**Обязательно!** Иначе программа завершится с ошибкой (п. 6.2 ТЗ).

Способ 1 — через контекстное меню:
- ПКМ по `cmd` → `Запуск от имени администратора`
- Перейти в папку проекта: `cd C:\share_backups`
- Выполнить: `pipenv run python main.py`

Способ 2 — через PowerShell от админа:
```powershell
cd C:\share_backups
pipenv shell
python main.py
```

### 10.2. Создание мастер-пароля

При первом запуске программа обнаружит отсутствие `credentials.bin` и откроет диалог создания мастер-пароля (п. 1.3 ТЗ).

**Требования к мастер-паролю:**
- Минимум 12 символов
- Рекомендуется использовать парольную фразу (например: `MyB@ckup2026!Secure`)
- **Запишите пароль в надёжное место** — без него бэкапы будут недоступны

После создания:
- Файл `credentials.bin` будет создан в папке `data\`
- Содержит: `salt (16 байт) + hash (32 байта, PBKDF2-SHA256, 100 000 итераций)`

### 10.3. Настройка шар

В главном окне перейдите в раздел **Конфигурация → Шары** и добавьте:
- `share_nic`: короткое имя (например, `docs`)
- `share_name`: UNC-путь (`\\fileserver\documents`)
- `login`: учётные данные (`DOMAIN\username` или `.\username`)
- `password`: пароль (шифруется AES-256 ключом, производным от мастер-пароля)
- `mt_threads`: 8 (по умолчанию)

### 10.4. Настройка расписания

В разделе **Конфигурация → Расписание** добавьте cron-профили:
- Полный бэкап: `0 2 * * 0` (каждое воскресенье в 02:00)
- Инкрементальный: `0 2 * * 1-6` (понедельник-суббота в 02:00)

### 10.5. Указание целевой папки

В разделе **Конфигурация → Общие**:
- `target_backup_path`: путь к локальному диску/папке для хранения бэкапов (например, `D:\Backups`)
- Убедитесь, что на этом диске достаточно места

---

## 11. Ручной запуск первого бэкапа для проверки

В главном окне нажмите кнопку **«Запустить полный бэкап сейчас»** (или дождитесь срабатывания cron).

### Контроль процесса:
1. Индикатор состояния должен переключиться в `running`
2. В папке `D:\Backups` появится `backup_1_YYYYMMDD_HHMMSS_temp\`
3. Внутри — подпапки для каждой шары (`docs\`, `projects\` и т.д.)
4. После завершения — папка переименуется в `backup_1_..._main`
5. Индикатор вернётся в `idle`
6. В `backup_log` появится запись со статусом `success`

### Проверка БД:
```cmd
pipenv run python -c "import sqlite3; c=sqlite3.connect('data/share_backups.db'); print(c.execute('SELECT * FROM backup_log').fetchall())"
```

---

## 12. Проверка VSS

Убедитесь, что служба теневого копирования запущена:

```cmd
sc query vss
```

Если служба остановлена:
```cmd
net start vss
```

Для автоматического запуска:
```cmd
sc config vss start= auto
```

Проверка создания теневой копии вручную (от админа):
```cmd
vssadmin list shadows
```

---

## 13. Добавление в автозагрузку

Чтобы программа запускалась при старте Windows:

1. Создайте ярлык для `pipenv run python C:\share_backups\main.py`
2. Поместите ярлык в:
   ```
   C:\ProgramData\Microsoft\Windows\Start Menu\Programs\Startup\
   ```
3. В свойствах ярлыка → Дополнительно → ✅ `Запуск от имени администратора`

> **Альтернатива:** использовать Планировщик задач Windows с триггером «При запуске» и флагом «Выполнять с наивысшими правами».

---

## 14. Сборка в .exe (опционально)

Для распространения без установки Python:

```cmd
pipenv install --dev
pipenv run pyinstaller --noconfirm --onedir --windowed ^
    --name share_backups ^
    --add-data "db\schema.sql;db" ^
    --add-data "config\settings.ini;config" ^
    --icon=ui\icon.ico ^
    --hidden-import=win32security ^
    --hidden-import=win32com ^
    --hidden-import=cryptography ^
    main.py
```

Готовый дистрибутив будет в папке `dist\share_backups\`.

---

## 15. Типовые проблемы и решения

| Проблема | Решение |
|---|---|
| `SSL: TLSV1_ALERT_PROTOCOL_VERSION` при `pip install` | Установить KB3140245 + перезагрузить ПК |
| `ImportError: No module named win32security` | Переустановить pywin32: `pipenv run pip install --force-reinstall pywin32` |
| `Access is denied` при создании VSS | Запускать программу строго от Администратора |
| `robocopy not found` | Проверить, что файл `C:\Windows\System32\robocopy.exe` существует |
| Бэкап уходит в `no_space` | Увеличить свободное место на целевом диске (нужно размер данных + 10%) |
| Заблокированные файлы не копируются | Проверить, что служба VSS запущена (`net start vss`) |
| Ошибка `database is locked` | Убедиться, что запущен только один экземпляр программы (мьютекс) |

---

## 16. Структура данных после инициализации

```
C:\share_backups\
├── Pipfile
├── Pipfile.lock
├── main.py
├── auth/ config/ db/ backup/ restore/ ui/ scheduler/
├── data/
│   ├── share_backups.db          # SQLite БД
│   ├── credentials.bin           # Хэш мастер-пароля
│   └── settings.ini              # Конфигурация
└── dist/                         # (опционально) собранный .exe
```

---

## 17. Резервная копия конфигурации

**Критически важные файлы для восстановления:**
- `data/credentials.bin` — без него невозможен доступ к бэкапам
- `data/share_backups.db` — метаданные всех бэкапов
- `data/settings.ini` — конфигурация шар и расписания

Рекомендуется периодически копировать папку `data/` на внешний носитель.

---

После выполнения всех шагов система готова к работе. Первый полный бэкап рекомендуется запустить вручную и дождаться завершения перед настройкой автоматического расписания.