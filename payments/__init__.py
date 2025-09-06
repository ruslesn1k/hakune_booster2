from .payment_states import PaymentStates
from .paypalych import pally_router
from .yookassa import yookassa_router
from .yoomoney import yoomoney_router
from .telegram_stars import stars_router

routers = [r for r in (pally_router, yookassa_router, yoomoney_router, stars_router) if r]
