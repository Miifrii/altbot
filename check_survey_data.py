"""
Скрипт для проверки данных опросов в БД
"""
import sqlite3
import os

DB_PATH = os.path.join("data", "bot.db")

def check_survey_data():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    print("=" * 60)
    print("📊 ПРОВЕРКА ДАННЫХ ОПРОСОВ")
    print("=" * 60)
    
    # 1. Список опросов
    print("\n1️⃣ ОПРОСЫ:")
    surveys = cursor.execute("SELECT * FROM surveys").fetchall()
    if surveys:
        for s in surveys:
            print(f"   ID: {s['id']} | {s['title']} | Статус: {s['status']}")
    else:
        print("   ❌ Нет опросов")
    
    # 2. Вопросы
    print("\n2️⃣ ВОПРОСЫ:")
    questions = cursor.execute("SELECT * FROM survey_questions").fetchall()
    if questions:
        for q in questions:
            print(f"   ID: {q['id']} | Опрос: {q['survey_id']} | {q['question_text'][:50]}...")
    else:
        print("   ❌ Нет вопросов")
    
    # 3. Сессии (кто проходил)
    print("\n3️⃣ СЕССИИ (кто проходил):")
    sessions = cursor.execute("""
        SELECT ss.*, s.title 
        FROM survey_sessions ss
        JOIN surveys s ON ss.survey_id = s.id
        ORDER BY ss.started_at DESC
    """).fetchall()
    if sessions:
        for sess in sessions:
            status = "✅ Завершен" if sess['completed_at'] else "⏳ В процессе"
            print(f"   User ID: {sess['user_id']} | Опрос: {sess['title']} | {status}")
    else:
        print("   ❌ Никто не проходил опросы")
    
    # 4. Ответы
    print("\n4️⃣ ОТВЕТЫ:")
    responses = cursor.execute("""
        SELECT COUNT(*) as cnt FROM survey_responses
    """).fetchone()
    print(f"   Всего ответов: {responses['cnt']}")
    
    # 5. Детальная статистика по опросам
    print("\n5️⃣ СТАТИСТИКА ПО ОПРОСАМ:")
    for survey in surveys:
        survey_id = survey['id']
        
        # Сколько начали
        started = cursor.execute(
            "SELECT COUNT(*) as cnt FROM survey_sessions WHERE survey_id=?",
            (survey_id,)
        ).fetchone()['cnt']
        
        # Сколько завершили
        completed = cursor.execute(
            "SELECT COUNT(*) as cnt FROM survey_sessions WHERE survey_id=? AND completed_at IS NOT NULL",
            (survey_id,)
        ).fetchone()['cnt']
        
        # Сколько вопросов
        q_count = cursor.execute(
            "SELECT COUNT(*) as cnt FROM survey_questions WHERE survey_id=?",
            (survey_id,)
        ).fetchone()['cnt']
        
        print(f"\n   📋 {survey['title']} (ID: {survey_id})")
        print(f"      Вопросов: {q_count}")
        print(f"      Начали: {started}")
        print(f"      Завершили: {completed}")
        if started > 0:
            print(f"      Процент: {completed/started*100:.1f}%")
    
    # 6. Последние 5 ответов
    print("\n6️⃣ ПОСЛЕДНИЕ 5 ОТВЕТОВ:")
    recent = cursor.execute("""
        SELECT 
            sr.answer,
            sq.question_text,
            ss.user_id,
            sr.answered_at
        FROM survey_responses sr
        JOIN survey_questions sq ON sr.question_id = sq.id
        JOIN survey_sessions ss ON sr.session_id = ss.id
        ORDER BY sr.answered_at DESC
        LIMIT 5
    """).fetchall()
    if recent:
        for r in recent:
            print(f"   User {r['user_id']}: {r['question_text'][:40]}... → {r['answer'][:30]}")
    else:
        print("   ❌ Нет ответов")
    
    print("\n" + "=" * 60)
    print("✅ Проверка завершена!")
    print("=" * 60)
    
    conn.close()

if __name__ == "__main__":
    if not os.path.exists(DB_PATH):
        print(f"❌ Файл {DB_PATH} не найден!")
    else:
        check_survey_data()
