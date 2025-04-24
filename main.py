from bot import bot
from database import init_db

def main():
    init_db()
    bot.polling(none_stop=True)

if __name__ == "__main__":
    main()
