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


@pytest.mark.asyncio
async def test_run_episode_with_mock_provider(tmp_path: Path) -> None:
    import asyncio

    from showbible.tui.app import ShowBibleApp
    from showbible.tui.widgets.sidebar import SidebarSelection
    from showbible.vault import ensure_episode

    vault = init_vault(tmp_path / "Demo")
    ensure_episode(vault, "S01E01")
    app = ShowBibleApp(vault=vault, episode_id="S01E01", provider="mock")
    async with app.run_test() as pilot:
        await pilot.pause()
        app.post_message(SidebarSelection(section="command", key="run"))
        await pilot.pause()
        # wait until the worker finishes (mock provider is fast)
        for _ in range(50):
            if app.state.runs:
                handle = next(iter(app.state.runs.values()))
                if handle.status in {"complete", "failed"}:
                    break
            await asyncio.sleep(0.1)
        assert app.state.runs
        handle = next(iter(app.state.runs.values()))
        assert handle.status == "complete", handle.error


@pytest.mark.asyncio
async def test_arc_suggest_modal_with_stub_provider(tmp_path: Path, monkeypatch) -> None:
    import asyncio

    from showbible.tui.app import ShowBibleApp
    from showbible.tui.panes.arc import ArcAction
    from showbible.tui.screens.ai_suggest import AISuggestScreen
    from showbible.vault import ensure_episode

    vault = init_vault(tmp_path / "Demo")
    ensure_episode(vault, "S01E01")

    class Provider:
        name = "stub"

        def generate(self, phase, episode_id, prompt):
            return type(
                "Generation",
                (),
                {
                    "text": '[{"episode":"S01E01","status":"planned","beat":"raise the stakes"}]',
                    "tokens": 0,
                    "dollars": 0.0,
                },
            )()

    monkeypatch.setattr("showbible.cli.resolve_provider", lambda name: Provider())

    app = ShowBibleApp(vault=vault, episode_id="S01E01", provider="stub")
    async with app.run_test() as pilot:
        await pilot.pause()
        app.post_message(ArcAction(action="suggest", arc_slug="season-theme"))
        await pilot.pause()
        # AISuggestScreen mounts; let the worker finish
        for _ in range(30):
            await asyncio.sleep(0.1)
            if isinstance(app.screen, AISuggestScreen):
                if app.screen.query("SelectionList"):
                    break
        assert isinstance(app.screen, AISuggestScreen)
        assert app.screen.query("SelectionList")
