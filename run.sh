#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

if [[ ! -x .venv/bin/python ]]; then
	echo "未找到 .venv，请先执行: python3 -m venv .venv && . .venv/bin/activate && python -m pip install -r requirements.txt"
	exit 1
fi

. .venv/bin/activate
python main.py
