"""
Пример создания опроса программно.
Этот скрипт можно использовать для быстрого создания тестового опроса.
"""
from database_surveys import *


def create_example_survey(guild_id: int, admin_id: int, results_channel_id: int = None):
    """
    Создает пример опроса "Опрос проекта".
    
    Args:
        guild_id: ID сервера Discord
        admin_id: ID администратора, создающего опрос
        results_channel_id: ID канала для результатов (опционально)
    
    Returns:
        survey_id: ID созданного опроса
    """
    
    # Создаем опрос
    survey_id = create_survey(
        guild_id=guild_id,
        title="Опрос проекта",
        description="Помогите нам улучшить проект, ответив на несколько вопросов",
        anonymous=False,
        created_by=admin_id,
        results_channel_id=results_channel_id
    )
    
    print(f"✅ Создан опрос ID: {survey_id}")
    
    # Категория 1: Общие впечатления
    cat1_id = add_category(
        survey_id=survey_id,
        title="Общие впечатления",
        description="Ваше общее мнение о проекте",
        order_index=0
    )
    
    add_question(
        category_id=cat1_id,
        question_text="Как вы оцениваете проект в целом?",
        question_type="rating",
        required=True,
        order_index=0
    )
    
    add_question(
        category_id=cat1_id,
        question_text="Что вам больше всего нравится в проекте?",
        question_type="text",
        required=True,
        order_index=1
    )
    
    add_question(
        category_id=cat1_id,
        question_text="Что бы вы хотели улучшить?",
        question_type="text",
        required=False,
        order_index=2
    )
    
    print(f"✅ Добавлена категория: Общие впечатления ({cat1_id})")
    
    # Категория 2: Работа администрации
    cat2_id = add_category(
        survey_id=survey_id,
        title="Работа администрации",
        description="Оцените работу администрации проекта",
        order_index=1
    )
    
    add_question(
        category_id=cat2_id,
        question_text="Как вы оцениваете работу администрации?",
        question_type="rating",
        required=True,
        order_index=0
    )
    
    add_question(
        category_id=cat2_id,
        question_text="Насколько быстро администрация реагирует на проблемы?",
        question_type="rating",
        required=True,
        order_index=1
    )
    
    add_question(
        category_id=cat2_id,
        question_text="Есть ли у вас предложения для администрации?",
        question_type="text",
        required=False,
        order_index=2
    )
    
    print(f"✅ Добавлена категория: Работа администрации ({cat2_id})")
    
    # Категория 3: Модерация Discord
    cat3_id = add_category(
        survey_id=survey_id,
        title="Модерация Discord",
        description="Оцените работу модераторов на сервере",
        order_index=2
    )
    
    add_question(
        category_id=cat3_id,
        question_text="Как вы оцениваете работу модераторов?",
        question_type="rating",
        required=True,
        order_index=0
    )
    
    add_question(
        category_id=cat3_id,
        question_text="Чувствуете ли вы себя в безопасности на сервере?",
        question_type="rating",
        required=True,
        order_index=1
    )
    
    print(f"✅ Добавлена категория: Модерация Discord ({cat3_id})")
    
    # Категория 4: Игровой процесс
    cat4_id = add_category(
        survey_id=survey_id,
        title="Игровой процесс",
        description="Ваше мнение об игровом процессе",
        order_index=3
    )
    
    add_question(
        category_id=cat4_id,
        question_text="Насколько интересен игровой процесс?",
        question_type="rating",
        required=True,
        order_index=0
    )
    
    add_question(
        category_id=cat4_id,
        question_text="Что вам нравится в игровом процессе?",
        question_type="text",
        required=False,
        order_index=1
    )
    
    add_question(
        category_id=cat4_id,
        question_text="Какие механики вы бы добавили?",
        question_type="text",
        required=False,
        order_index=2
    )
    
    print(f"✅ Добавлена категория: Игровой процесс ({cat4_id})")
    
    # Категория 5: Баланс
    cat5_id = add_category(
        survey_id=survey_id,
        title="Баланс",
        description="Оцените баланс игры",
        order_index=4
    )
    
    add_question(
        category_id=cat5_id,
        question_text="Насколько сбалансирована игра?",
        question_type="rating",
        required=True,
        order_index=0
    )
    
    add_question(
        category_id=cat5_id,
        question_text="Какие аспекты требуют балансировки?",
        question_type="text",
        required=False,
        order_index=1
    )
    
    print(f"✅ Добавлена категория: Баланс ({cat5_id})")
    
    # Категория 6: Предложения и идеи
    cat6_id = add_category(
        survey_id=survey_id,
        title="Предложения и идеи",
        description="Поделитесь своими идеями",
        order_index=5
    )
    
    add_question(
        category_id=cat6_id,
        question_text="Какие новые функции вы бы хотели видеть?",
        question_type="text",
        required=False,
        order_index=0
    )
    
    add_question(
        category_id=cat6_id,
        question_text="Есть ли у вас другие предложения?",
        question_type="text",
        required=False,
        order_index=1
    )
    
    add_question(
        category_id=cat6_id,
        question_text="Порекомендуете ли вы проект друзьям?",
        question_type="rating",
        required=True,
        order_index=2
    )
    
    print(f"✅ Добавлена категория: Предложения и идеи ({cat6_id})")
    
    # Получаем статистику
    questions = get_all_survey_questions(survey_id)
    categories = get_survey_categories(survey_id)
    
    print(f"\n📊 Итого:")
    print(f"   Категорий: {len(categories)}")
    print(f"   Вопросов: {len(questions)}")
    print(f"\n💡 Опрос готов! Используйте команду:")
    print(f"   /surveyadmin publish survey_id:{survey_id}")
    
    return survey_id


if __name__ == "__main__":
    # Инициализируем БД
    init_surveys_db()
    
    # Пример использования
    # Замените значения на реальные
    GUILD_ID = 123456789  # ID вашего сервера
    ADMIN_ID = 987654321  # ID администратора
    RESULTS_CHANNEL_ID = None  # ID канала для результатов (или None)
    
    print("⚠️  Внимание! Этот скрипт создаст тестовый опрос.")
    print("⚠️  Убедитесь, что вы изменили GUILD_ID и ADMIN_ID на реальные значения!\n")
    
    # Раскомментируйте для создания опроса:
    # survey_id = create_example_survey(GUILD_ID, ADMIN_ID, RESULTS_CHANNEL_ID)
    
    print("\n❌ Скрипт не выполнен. Раскомментируйте последнюю строку для создания опроса.")
