#!/usr/bin/env python3
"""校验 TableCodeAgent 开发 prompt 是否保留关键结构和质量约束。

本脚本只检查 prompt 模板或生成物中是否出现必要的执行约束，不负责判断
具体任务内容是否已经完全覆盖用户意图，也不替代人工审查真实调用链和验证方案。
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Rule:
    message: str
    needles: tuple[str, ...] = ()
    any_of: tuple[str, ...] = ()

    def matches(self, text: str) -> bool:
        if self.needles and not all(needle in text for needle in self.needles):
            return False
        if self.any_of and not any(needle in text for needle in self.any_of):
            return False
        return True


def read_utf8(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"UTF-8 读取失败：{exc}") from exc
    except OSError as exc:
        raise ValueError(f"文件读取失败：{exc}") from exc


def build_rules() -> list[Rule]:
    fixed_sections = (
        "【硬性前置要求（必须先做）】",
        "【项目定位与边界】",
        "【版本、文档与报告策略】",
        "【本次要完成的 TODO，必须全部落地】",
        "【实现约束】",
        "【测试与验证要求，必须执行】",
        "【交付物要求】",
        "【注意】",
    )
    return [
        Rule("缺少任务开场中的仓库路径或“当前仓库”。", any_of=("当前仓库", "{{仓库路径")),
        Rule("缺少固定章节。", needles=fixed_sections),
        Rule(
            "缺少先读项目规则、README 和真实调用链的要求。",
            needles=(".codex/AGENTS.md", "README.md", "真实调用链"),
        ),
        Rule(
            "缺少真实仓库结构、真实调用链和真实测试入口要求。",
            needles=("真实仓库结构", "真实调用链", "真实测试入口"),
        ),
        Rule(
            "缺少简体中文规则。",
            needles=("简体中文", "代码", "命令", "文件路径"),
        ),
        Rule(
            "缺少 TableCodeAgent 项目定位。",
            needles=("TableCodeAgent", "复杂表格任务", "轻量级 Coding Agent"),
        ),
        Rule(
            "缺少不能包装成其他项目类型的边界。",
            needles=("普通数据分析 Agent", "SFT", "RL", "RAG", "SOTA"),
        ),
        Rule(
            "缺少版本、文档与报告策略。",
            needles=("沿用当前仓库版本", "不主动 bump", "修复报告"),
        ),
        Rule("缺少 TODO 分块结构。", needles=("A.", "B.")),
        Rule(
            "缺少最小必要改动约束。",
            needles=("最小必要改动", "无关重构"),
        ),
        Rule(
            "缺少未验证、SKIP 和推测边界。",
            needles=("未验证", "SKIP", "推测"),
        ),
        Rule(
            "缺少 no-helper benchmark 边界。",
            needles=(
                "no-helper",
                "implementation_hints",
                "allowed_project_helpers",
                "solve_py_suggestion",
                "完整 workflow import",
                "build_*_report()",
            ),
        ),
        Rule(
            "缺少结构化输出机器可校验要求。",
            needles=("Agent 输出 JSON", "answer.json", "tool input", "output_contract", "机器可校验"),
        ),
        Rule(
            "缺少 API/env/key 安全边界。",
            needles=("configs/api/local/", ".env", "API key"),
        ),
        Rule(
            "缺少真实 API SKIP 边界。",
            needles=("env", "网络", "SKIP"),
        ),
        Rule(
            "缺少交付物要求。",
            needles=("文件改动清单", "验证命令", "证据路径", "风险与未验证项"),
        ),
    ]


def validate_rules(text: str) -> list[str]:
    return [rule.message for rule in build_rules() if not rule.matches(text)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "检查 TableCodeAgent 开发 prompt 模板或生成物是否保留关键执行约束；"
            "不判断具体任务内容是否完全覆盖用户意图。"
        )
    )
    parser.add_argument("prompt_path", help="目标 prompt-template.md 或生成出的 prompt 文件路径")
    args = parser.parse_args(argv)

    try:
        text = read_utf8(Path(args.prompt_path))
    except ValueError as exc:
        print(f"失败：{exc}")
        return 1

    missing = validate_rules(text)
    if missing:
        print("失败：TableCodeAgent 开发 prompt 缺少以下关键约束：")
        for item in missing:
            print(f"- {item}")
        return 1

    print("通过：TableCodeAgent 开发 prompt 关键约束检查通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
