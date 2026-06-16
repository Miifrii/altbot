#!/bin/bash

# Скрипт экспорта SQLite базы с Railway
# Требуется: установленный Railway CLI и авторизация

echo "🚂 Экспорт базы данных с Railway..."

# Проверяем Railway CLI
if ! command -v railway &> /dev/null; then
    echo "❌ Railway CLI не найден. Установите: npm install -g @railway/cli"
    exit 1
fi

# Проверяем авторизацию
if ! railway whoami &> /dev/null; then
    echo "❌ Не авторизованы. Выполните: railway login"
    exit 1
fi

# Создаём папку для бэкапов
mkdir -p backups
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="backups/bot_db_${TIMESTAMP}.db"
SQL_DUMP="backups/bot_db_${TIMESTAMP}.sql"

echo "📦 Экспорт в: $BACKUP_FILE"

# Скачиваем файл БД через railway run
railway run sqlite3 $DATA_DIR/bot.db ".dump" > "$SQL_DUMP"

if [ $? -eq 0 ]; then
    echo "✅ SQL-дамп сохранён: $SQL_DUMP"
    
    # Также создаём бинарную копию
    railway run cat $DATA_DIR/bot.db > "$BACKUP_FILE"
    
    if [ $? -eq 0 ]; then
        echo "✅ Бинарная копия сохранена: $BACKUP_FILE"
    fi
else
    echo "❌ Ошибка экспорта"
    exit 1
fi

echo "📊 Размер файла: $(du -h $BACKUP_FILE | cut -f1)"
echo "✨ Готово!"
