import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from bot.ui import build_bot_commands, build_main_menu, configure_bot_ui


class TelegramUiTests(unittest.TestCase):
    def test_build_bot_commands_includes_primary_commands(self) -> None:
        commands = build_bot_commands()

        self.assertEqual(commands[0].command, "start")
        self.assertIn("funding_diff", [command.command for command in commands])
        self.assertIn("frequency", [command.command for command in commands])
        self.assertIn("help", [command.command for command in commands])

    def test_build_main_menu_is_persistent_and_clickable(self) -> None:
        markup = build_main_menu()
        button_rows = [[button.text for button in row] for row in markup.keyboard]

        self.assertTrue(markup.is_persistent)
        self.assertTrue(markup.resize_keyboard)
        self.assertEqual(button_rows[0], ["/negative", "/positive"])
        self.assertIn("/funding_diff", button_rows[1])
        self.assertIn("/help", button_rows[-1])


class ConfigureBotUiTests(unittest.IsolatedAsyncioTestCase):
    async def test_configure_bot_ui_registers_bot_commands(self) -> None:
        set_my_commands = AsyncMock()
        application = SimpleNamespace(bot=SimpleNamespace(set_my_commands=set_my_commands))

        await configure_bot_ui(application)

        set_my_commands.assert_awaited_once()
        registered_commands = set_my_commands.await_args.args[0]
        self.assertEqual(registered_commands[0].command, "start")
        self.assertEqual(registered_commands[-1].command, "help")


if __name__ == "__main__":
    unittest.main()
