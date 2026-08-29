import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
import os

# Токен из переменных окружения Render
TOKEN = os.environ.get("8942158039:AAEqukimot3xatu1UPD6toC9kg8cCW4b0Ns")
logging.basicConfig(level=logging.INFO)

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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎮 Игра Крестики-Нолики\n"
        "Используйте /play @username, чтобы начать игру с другим игроком.\n"
        "Или /play чтобы сыграть с ботом."
    )

async def play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    player1 = update.effective_user.username or str(update.effective_user.id)
    
    if args:
        player2 = args[0].replace('@', '')
    else:
        player2 = "Bot"

    if player1 == player2:
        await update.message.reply_text("❌ Нельзя играть самим с собой!")
        return

    game_id = f"{update.effective_chat.id}_{player1}_{player2}"
    games[game_id] = TicTacToe(player1, player2)
    game = games[game_id]

    await update.message.reply_text(
        f"🆕 Игра началась!\n{game.get_status()}",
        reply_markup=game.get_keyboard()
    )

async def handle_move(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
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
        await query.edit_message_text("❌ Игра не найдена")
        return

    current_player = game.players[game.current]
    if str(user) != current_player and current_player != "Bot":
        await query.answer("⛔ Сейчас не ваш ход!")
        return

    if not game.make_move(pos):
        await query.answer("❌ Клетка занята!")
        return

    if game.winner or game.is_draw():
        await query.edit_message_text(
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

    await query.edit_message_text(
        f"{game.get_status()}",
        reply_markup=game.get_keyboard()
    )

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("play", play))
    app.add_handler(CallbackQueryHandler(handle_move, pattern="^move_"))
    app.run_polling()

if __name__ == "__main__":
    main()
