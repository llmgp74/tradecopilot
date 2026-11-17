.PHONY: macos windows-arm64 windows-x64

# Stages the agent source, builds the frontend, compiles the Tauri shell, and
# bundles TradeCopilot.app, then replaces the installed copy and opens it.
macos:
	npm --prefix ui run tauri build
	-osascript -e 'quit app "TradeCopilot"'
	rm -rf /Applications/TradeCopilot.app
	ditto ui/src-tauri/target/release/bundle/macos/TradeCopilot.app /Applications/TradeCopilot.app
	open /Applications/TradeCopilot.app

# Builds the NSIS installer, replaces the per-user install, and opens it.
windows-arm64:
	npm --prefix ui run tauri build
	-powershell -NoProfile -Command 'Get-Process tradecopilot-ui -ErrorAction SilentlyContinue | Stop-Process -Force'
	powershell -NoProfile -Command '$$setup = Get-ChildItem "ui/src-tauri/target/release/bundle/nsis/*.exe" | Select-Object -First 1; Start-Process -FilePath $$setup.FullName -ArgumentList "/S" -Wait'
	powershell -NoProfile -Command 'Start-Process (Join-Path $$env:LOCALAPPDATA "TradeCopilot/tradecopilot-ui.exe")'

# Builds the x64 installer, replaces the per-user install, and opens it. Also
# cross-builds from an ARM64 host, where the app runs under x64 emulation.
windows-x64:
	rustup target add x86_64-pc-windows-msvc
	npm --prefix ui run tauri build -- --target x86_64-pc-windows-msvc
	-powershell -NoProfile -Command 'Get-Process tradecopilot-ui -ErrorAction SilentlyContinue | Stop-Process -Force'
	powershell -NoProfile -Command '$$setup = Get-ChildItem "ui/src-tauri/target/x86_64-pc-windows-msvc/release/bundle/nsis/*.exe" | Select-Object -First 1; Start-Process -FilePath $$setup.FullName -ArgumentList "/S" -Wait'
	powershell -NoProfile -Command 'Start-Process (Join-Path $$env:LOCALAPPDATA "TradeCopilot/tradecopilot-ui.exe")'
