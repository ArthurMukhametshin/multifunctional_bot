import os
from PIL import Image, ImageDraw, ImageFont

def wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int):
    """
    Вспомогательная функция для переноса текста на новую строку.
    (Эта функция остается без изменений).
    """
    lines = []
    if font.getbbox(text)[2] <= max_width:
        lines.append(text)
    else:
        words = text.split(' ')
        i = 0
        while i < len(words):
            line = ''
            while i < len(words) and font.getbbox(line + words[i])[2] <= max_width:
                line = line + words[i] + " "
                i += 1
            if not line:
                line = words[i]
                i += 1
            lines.append(line.strip())
    return lines

def draw_text_block(draw, text, x_pos, y_start, font, max_width, line_spacing):
    """
    Рисует текстовый блок с автопереносом и возвращает новую Y-координату
    (положение курсора ПОСЛЕ этого блока).
    """
    lines = wrap_text(text, font, max_width)
    current_y = y_start
    for line in lines:
        draw.text((x_pos, current_y), line, font=font, fill="black")
        # Смещаемся вниз на высоту строки + межстрочный интервал
        current_y += font.getbbox(line)[3] + line_spacing
    return current_y


def generate_ticket_image(event_name: str, fio: str, date_str: str, address: str) -> str:
    """
    Генерирует изображение билета с ДИНАМИЧЕСКИМ позиционированием текста.
    """
    try:
        template_path = "ticket_template.jpg"
        img = Image.open(template_path)
        draw = ImageDraw.Draw(img)

        # --- НАСТРОЙКИ ВНЕШНЕГО ВИДА ---
        # Шрифты
        bold_font_path = "Montserrat-Bold.ttf"
        regular_font_path = "Montserrat-Regular.ttf"
        font_event = ImageFont.truetype(bold_font_path, size=100)
        font_details = ImageFont.truetype(regular_font_path, size=90)

        # Отступы и позиционирование
        START_X = 280  # Горизонтальный отступ слева
        START_Y = 180  # Вертикальный отступ для самого первого элемента
        MAX_TEXT_WIDTH = 1500  # Максимальная ширина текстового блока

        # Промежутки между элементами
        LINE_SPACING = 0  # Расстояние между строками ВНУТРИ одного блока (название, фио)
        BLOCK_SPACING = 100  # Расстояние МЕЖДУ блоками (между названием и ФИО, между ФИО и датой)

        # --- ПРОЦЕСС РИСОВАНИЯ ---
        # Инициализируем наш "Y-курсор"
        current_y = START_Y

        # 1. Рисуем НАЗВАНИЕ МЕРОПРИЯТИЯ
        # Функция вернет новую позицию курсора после отрисовки всего блока
        new_y_after_event = draw_text_block(
            draw, event_name, START_X, current_y, font_event, MAX_TEXT_WIDTH, LINE_SPACING
        )
        current_y = new_y_after_event

        # 2. Добавляем отступ и рисуем ФИО
        current_y += BLOCK_SPACING  # Добавляем большой отступ между блоками
        new_y_after_fio = draw_text_block(
            draw, fio, START_X, current_y, font_details, MAX_TEXT_WIDTH, LINE_SPACING
        )
        current_y = new_y_after_fio

        # 3. Добавляем отступ и рисуем ДАТУ
        current_y += BLOCK_SPACING
        new_y_after_date = draw_text_block(
            draw, date_str, START_X, current_y, font_details, MAX_TEXT_WIDTH, LINE_SPACING
        )
        current_y = new_y_after_date

        # 4. Добавляем отступ и рисуем АДРЕС
        current_y += BLOCK_SPACING
        draw_text_block(
            draw, address, START_X, current_y, font_details, MAX_TEXT_WIDTH, LINE_SPACING
        )

        # Сохраняем результат
        output_path = f"generated_tickets/ticket_{fio.replace(' ', '_')}.png"
        img.save(output_path)
        return output_path

    except FileNotFoundError as e:
        print(f"Ошибка: Не найден файл шаблона или шрифта! Проверьте: {e}")
        return None
    except Exception as e:
        print(f"Ошибка при генерации билета: {e}")
        return None


import os

if not os.path.exists('generated_tickets'):
    os.makedirs('generated_tickets')