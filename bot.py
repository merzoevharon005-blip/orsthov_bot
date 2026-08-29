import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, CallbackContext

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("BOT_TOKEN", "8942158039:AAEqukimot3xatu1UPD6toC9kg8cCW4b0Ns")

games = {}

class TicTacToe:
    def __init__(self, player1, player2):
        self.board = [' '] * 9
        self.players = [player1, player2]
        self.current = 0
        self.winner = None

    def make_move(self, pos):
        if self.board[pos] == ' ' and not self.winner:
            self.board[pos] = 'X' if self.current == 0 else 'O'
            if self.check_win():
                self.winner = self.players[self.current]
            else:
                self.current ^= 1
            return True
        return False

    def check_win(self):
        win_patterns = [(0,1,2),(3,4,5),(6,7,8),(0,3,6),(1,4,7),(2,5,8),(0,4,8),(2,4,6)]
        symbol = 'X' if self.current == 0 else 'O'
        return any(all(self.board[i] == symbol for i in p) for p in win_patterns)

    def is_draw(self):
        return ' ' not in self.board and not self.winner

    def get_keyboard(self):
        keyboard = []
        row = []
        for i in range(9):
            text = self.board[i] if self.board[i] != ' ' else str(i + 1)
            row.append(InlineKeyboardButton(text, callback_data=f"move_{i}"))
            if len(row) == 3:
                keyboard.append(row)
                row = []
        return InlineKeyboardMarkup(keyboard)

    def get_status(self):
        if self.winner:
            return f"🏆 Победил {self.winner}!"
        elif self.is_draw():
            return "🤝 Ничья!"
        else:
            return f"Ход игрока {self.players[self.current]} ({'X' if self.current == 0 else 'O'})"

def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        "🎮 Игра Крестики-Нолики\n"
        "Используйте /play @username, чтобы начать игру с другим игроком.\n"
        "Или /play чтобы сыграть с ботом."
    )

def play(update: Update, context: CallbackContext):
    args = context.args
    player1 = update.effective_user.username or str(update.effective_user.id)
    
    if args:
        player2 = args[0].replace('@', '')
    else:
        player2 = "Bot"

    if player1 == player2:
        update.message.reply_text("❌ Нельзя играть самим с собой!")
        return

    game_id = f"{update.effective_chat.id}_{player1}_{player2}"
    games[game_id] = TicTacToe(player1, player2)
    game = games[game_id]

    update.message.reply_text(
        f"🆕 Игра началась!\n{game.get_status()}",
        reply_markup=game.get_keyboard()
    )

def handle_move(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    
    pos = int(query.data.split('_')[1])
    user = query.from_user.username or str(query.from_user.id)

    game_id = None
    game = None
    for gid, g in games.items():
        if str(user) in gid and str(update.effective_chat.id) in gid:
            game_id = gid
            game = g
            break

    if not game:
        query.edit_message_text("❌ Игра не найдена")
        return

    current_player = game.players[game.current]
    if str(user) != current_player and current_player != "Bot":
        query.answer("⛔ Сейчас не ваш ход!")
        return

    if not game.make_move(pos):
        query.answer("❌ Клетка занята!")
        return

    if game.winner or game.is_draw():
        query.edit_message_text(
            f"{game.get_status()}",
            reply_markup=None
        )
        del games[game_id]
        return

    if game.players[game.current] == "Bot":
        import random
        empty = [i for i, v in enumerate(game.board) if v == ' ']
        if empty:
            bot_move = random.choice(empty)
            game.make_move(bot_move)

    query.edit_message_text(
        f"{game.get_status()}",
        reply_markup=game.get_keyboard()
    )

def main():
    logger.info("🚀 Бот запускается...")
    updater = Updater(token=TOKEN, use_context=True)
    dp = updater.dispatcher
    
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("play", play))
    dp.add_handler(CallbackQueryHandler(handle_move, pattern="^move_"))
    
    logger.info("✅ Бот готов к работе!")
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
