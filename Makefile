.PHONY: macos windows

# Stages the agent source, builds the frontend, compiles the Tauri shell, and
# bundles TradeCopilot.app, then replaces the installed copy and opens it.
macos:
	npm --prefix ui run tauri build
	-osascript -e 'quit app "TradeCopilot"'
	rm -rf /Applications/TradeCopilot.app
	ditto ui/src-tauri/target/release/bundle/macos/TradeCopilot.app /Applications/TradeCopilot.app
	open /Applications/TradeCopilot.app

# Builds the NSIS installer, replaces the per-user install, and opens it.
windows:
	npm --prefix ui run tauri build
	-powershell -NoProfile -Command 'Get-Process tradecopilot-ui -ErrorAction SilentlyContinue | Stop-Process -Force'
	powershell -NoProfile -Command '$$setup = Get-ChildItem "ui/src-tauri/target/release/bundle/nsis/*.exe" | Select-Object -First 1; Start-Process -FilePath $$setup.FullName -ArgumentList "/S" -Wait'
	powershell -NoProfile -Command 'Start-Process (Join-Path $$env:LOCALAPPDATA "TradeCopilot/tradecopilot-ui.exe")'
