from slowapi import Limiter
from slowapi.util import get_remote_address

# ক্লায়েন্টের IP এড্রেস ধরে রেট লিমিটিং কাজ করবে
limiter = Limiter(key_func=get_remote_address)