from aiogram.fsm.state import State, StatesGroup

class Booking(StatesGroup):
    choosing_event = State()
    entering_name = State()
    entering_phone = State()
    waiting_for_promo = State()
    entering_promo_code = State()
    confirming_data = State()

class Feedback(StatesGroup):
    waiting_for_text = State()

class Checklists(StatesGroup):
    choosing_checklist = State()