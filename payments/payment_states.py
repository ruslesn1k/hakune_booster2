from aiogram.fsm.state import StatesGroup, State

class PaymentStates(StatesGroup):
    choosing_method = State()
    waiting_proof = State()
