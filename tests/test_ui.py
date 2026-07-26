import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from bot.ui import (
    build_bot_commands,
    build_main_menu,
    build_pagination_keyboard,
    configure_bot_ui,
)


class TelegramUiTests(unittest.TestCase):
    def test_build_bot_commands_includes_primary_commands(self) -> None:
        commands = build_bot_commands()

        self.assertEqual(commands[0].command, "start")
        self.assertIn("funding_diff", [command.command for command in commands])
        self.assertIn("frequency", [command.command for command in commands])
        self.assertIn("cooldown", [command.command for command in commands])
        self.assertIn("stop", [command.command for command in commands])
        self.assertIn("help", [command.command for command in commands])

    def test_build_main_menu_is_persistent_and_clickable(self) -> None:
        markup = build_main_menu()
        button_rows = [[button.text for button in row] for row in markup.keyboard]

        self.assertTrue(markup.is_persistent)
        self.assertTrue(markup.resize_keyboard)
        self.assertEqual(button_rows[0], ["/negative", "/positive"])
        self.assertIn("/funding_diff", button_rows[1])
        self.assertIn("/surge", button_rows[2])
        self.assertIn("/help", button_rows[-1])

    def test_pagination_keyboard_exposes_valid_navigation(self) -> None:
        first_page = build_pagination_keyboard("negative", 0, has_next=True)
        assert first_page is not None
        self.assertEqual(first_page.inline_keyboard[0][0].text, "Next ▶")
        self.assertEqual(
            first_page.inline_keyboard[0][0].callback_data,
            "page:negative:1",
        )

        middle_page = build_pagination_keyboard("turnover", 2, has_next=True)
        assert middle_page is not None
        self.assertEqual(
            [button.callback_data for button in middle_page.inline_keyboard[0]],
            ["page:turnover:1", "page:turnover:3"],
        )


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
