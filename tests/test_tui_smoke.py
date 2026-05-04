from __future__ import annotations

from pathlib import Path

import pytest

from showbible.vault import init_vault


@pytest.mark.asyncio
async def test_app_boots_and_shows_sidebar(tmp_path: Path) -> None:
    from showbible.tui.app import ShowBibleApp
    from showbible.tui.widgets.sidebar import Sidebar
    from showbible.vault import ensure_episode

    vault = init_vault(tmp_path / "Demo")
    ensure_episode(vault, "S01E01")
    app = ShowBibleApp(vault=vault, episode_id="S01E01", provider="mock")
    async with app.run_test() as pilot:
        await pilot.pause()
        sidebar = app.query_one(Sidebar)
        assert sidebar is not None
        assert app.state.show_name == vault.name
        assert app.state.current_episode == "S01E01"
        assert "S01E01" in app.state.episodes


@pytest.mark.asyncio
async def test_episodes_pane_lists_episodes(tmp_path: Path) -> None:
    from showbible.tui.app import ShowBibleApp
    from showbible.tui.panes.episodes import EpisodesPane
    from showbible.vault import ensure_episode

    vault = init_vault(tmp_path / "Demo")
    ensure_episode(vault, "S01E01")
    app = ShowBibleApp(vault=vault, episode_id="S01E01", provider="mock")
    async with app.run_test() as pilot:
        await pilot.pause()
        pane = app.query_one(EpisodesPane)
        list_widget = app.query_one("#episodes-list")
        assert list_widget.option_count >= 1


@pytest.mark.asyncio
async def test_navigate_through_all_panes(tmp_path: Path) -> None:
    from showbible.tui.app import ShowBibleApp
    from showbible.tui.panes.arc import ArcPane
    from showbible.tui.panes.cast import CastPane
    from showbible.tui.panes.lore import LorePane
    from showbible.tui.panes.outputs import OutputsPane
    from showbible.tui.widgets.sidebar import SidebarSelection
    from showbible.vault import ensure_episode

    vault = init_vault(tmp_path / "Demo")
    ensure_episode(vault, "S01E01")
    app = ShowBibleApp(vault=vault, episode_id="S01E01", provider="mock")
    async with app.run_test() as pilot:
        await pilot.pause()
        for key, pane_cls in (("cast", CastPane), ("arc", ArcPane), ("lore", LorePane), ("outputs", OutputsPane)):
            app.post_message(SidebarSelection(section="nav", key=key))
            await pilot.pause()
            assert app.query(pane_cls)
