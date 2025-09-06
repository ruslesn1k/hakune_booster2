from aiogram.fsm.state import StatesGroup, State

class RegStates(StatesGroup):
    waiting_contact = State()
    waiting_nickname = State()