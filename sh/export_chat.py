"""SQLite 대화를 발표 준비용 Markdown으로 내보낸다. 원본 DB는 읽기 전용."""
import argparse
import sqlite3
from collections import defaultdict
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def export_chat(db: Path, output: Path, thread: str | None = None) -> int:
    with closing(sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        sql = "SELECT thread_id, role, content, created FROM messages"
        rows = connection.execute(sql + (" WHERE thread_id=?" if thread else "") + " ORDER BY rowid", (thread,) if thread else ()).fetchall()
    conversations = defaultdict(list)
    for thread_id, role, content, created in rows:
        conversations[thread_id].append((role, content, created))
    lines = ["# 채팅 시연 기록", "", "질문·최종 답변·저장 시각을 DB에서 내보낸 기록입니다. 진행 이벤트와 당시의 원시 조회값은 포함하지 않습니다.", ""]
    for thread_id, messages in conversations.items():
        lines.extend([f"## 대화: {thread_id}", ""])
        for role, content, created in messages:
            label = "질문" if role == "user" else "답변"
            lines.extend([f"### {label} — {created}", "", content, ""])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8")
    return len(rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=ROOT / "session.db")
    parser.add_argument("--out", type=Path, default=ROOT / "results" / "chat_history.md")
    parser.add_argument("--thread")
    args = parser.parse_args()
    print(f"Exported {export_chat(args.db, args.out, args.thread)} messages: {args.out.resolve()}")
