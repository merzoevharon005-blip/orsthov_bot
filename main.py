import logging
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils import executor

TOKEN = "8942158039:AAEqukimot3xatu1UPD6toC9kg8cCW4b0Ns"
bot = Bot(token=TOKEN)
dp = Dispatcher(bot)
logging.basicConfig(level=logging.INFO)

# Хранилище игр
games = {}

class TicTacToe:
    def __init__(self, player1, player2):
        self.board = [' '] * 9
        self.players = [player1, player2]  # [X, O]
        self.current = 0  # 0 - X, 1 - O
        self.winner = None

    def make_move(self, pos):
        if self.board[pos] == ' ' and not self.winner:
            self.board[pos] = 'X' if self.current == 0 else 'O'
            if self.check_win():
                self.winner = self.players[self.current]
            else:
                self.current ^= 1  # Переключение игрока
            return True
        return False

    def check_win(self):
        win_patterns = [(0,1,2),(3,4,5),(6,7,8),(0,3,6),(1,4,7),(2,5,8),(0,4,8),(2,4,6)]
        symbol = 'X' if self.current == 0 else 'O'
        return any(all(self.board[i] == symbol for i in p) for p in win_patterns)

    def is_draw(self):
        return ' ' not in self.board and not self.winner

    def get_keyboard(self):
        keyboard = InlineKeyboardMarkup(row_width=3)
        for i in range(9):
            text = self.board[i] if self.board[i] != ' ' else str(i + 1)
            keyboard.insert(InlineKeyboardButton(text, callback_data=f"move_{i}"))
        return keyboard

    def get_status(self):
        if self.winner:
            return f"🏆 Победил {self.winner}!"
        elif self.is_draw():
            return "🤝 Ничья!"
        else:
            return f"Ход игрока {self.players[self.current]} ({'X' if self.current == 0 else 'O'})"

@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    await message.answer(
        "🎮 Игра Крестики-Нолики\n"
        "Используйте /play @username, чтобы начать игру с другим игроком.\n"
        "Или /play чтобы сыграть с ботом."
    )

@dp.message_handler(commands=['play'])
async def play(message: types.Message):
    args = message.text.split()
    player1 = message.from_user.username or message.from_user.id

    if len(args) > 1:
        player2 = args[1].replace('@', '')
    else:
        player2 = "Bot"  # Игра с ботом

    if player1 == player2:
        await message.answer("❌ Нельзя играть самим с собой!")
        return

    game_id = f"{message.chat.id}_{player1}_{player2}"
    games[game_id] = TicTacToe(player1, player2)
    game = games[game_id]

    await message.answer(
        f"🆕 Игра началась!\n{game.get_status()}",
        reply_markup=game.get_keyboard()
    )

@dp.callback_query_handler(lambda c: c.data.startswith('move_'))
async def process_move(callback: types.CallbackQuery):
    pos = int(callback.data.split('_')[1])
    user = callback.from_user.username or callback.from_user.id

    # Поиск игры
    game_id = None
    game = None
    for gid, g in games.items():
        if str(user) in gid and str(callback.message.chat.id) in gid:
            game_id = gid
            game = g
            break

    if not game:
        await callback.answer("❌ Игра не найдена")
        return

    # Проверка очереди
    current_player = game.players[game.current]
    if str(user) != current_player and current_player != "Bot":
        await callback.answer("⛔ Сейчас не ваш ход!")
        return

    # Ход игрока
    if not game.make_move(pos):
        await callback.answer("❌ Клетка занята!")
        return

    # Проверка победы/ничьи
    if game.winner or game.is_draw():
        await callback.message.edit_text(
            f"{game.get_status()}",
            reply_markup=None
        )
        del games[game_id]
        return

    # Ход бота (если игра с ботом)
    if game.players[game.current] == "Bot":
        import random
        empty = [i for i, v in enumerate(game.board) if v == ' ']
        if empty:
            bot_move = random.choice(empty)
            game.make_move(bot_move)

    # Обновление доски
    await callback.message.edit_text(
        f"{game.get_status()}",
        reply_markup=game.get_keyboard()
    )
    await callback.answer()

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
