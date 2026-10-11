"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { ExamMarkdown } from "@/components/shared/exam-markdown";
import type { BankIssue, QuestionDetail } from "@/lib/api/exam-bank";

export function BankIssues({ issues }: { issues: BankIssue[] }) {
  return issues.length ? (
    <ul className="space-y-1 break-words text-sm">
      {issues.map((issue, index) => (
        <li key={`${issue.code}-${issue.path}-${index}`}>
          {issue.severity === "error" ? "错误" : "缺口 / 提示"}：{issue.code} ·{" "}
          {issue.path}
          {issue.question_number != null && ` · Q${issue.question_number}`}
        </li>
      ))}
    </ul>
  ) : (
    <p className="text-sm text-muted-foreground">
      未报告结构缺口；这不代表题文已验收。
    </p>
  );
}
export function BankDetail({ detail }: { detail: QuestionDetail }) {
  const [raw, setRaw] = useState(false);
  return (
    <>
      <p className="text-sm text-amber-700 dark:text-amber-300">
        管理预览含答案 · 未验收 · 用途未分配 · 不可练习
      </p>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 className="text-xl font-semibold">{detail.label}</h3>
        <Button variant="outline" onClick={() => setRaw(!raw)}>
          {raw ? "返回预览" : "查看原文"}
        </Button>
      </div>
      <p className="text-sm break-all">
        {detail.bank_name} · {detail.paper_ref ?? "来源卷号未知"} · 版本{" "}
        {detail.version_number}
        <br />
        {detail.source_path}
      </p>
      <p className="text-xs break-all text-muted-foreground">
        源文件 SHA-256：{detail.source_sha256}
      </p>
      <BankIssues issues={detail.issues} />
      {detail.unsupported_renderers.length > 0 && (
        <p role="note" className="rounded-lg border p-3">
          不支持的图形：{detail.unsupported_renderers.join("、")}
          。请核对下面的源码。
        </p>
      )}
      {detail.source_header && (
        <section>
          <h4 className="font-medium">共享上下文 / 来源文件头</h4>
          {raw ? (
            <pre className="overflow-auto whitespace-pre-wrap break-words text-sm">
              {detail.source_header}
            </pre>
          ) : (
            <ExamMarkdown
              content={detail.source_header}
              resources={detail.resources}
            />
          )}
        </section>
      )}
      {raw ? (
        <pre className="max-h-[70vh] overflow-auto whitespace-pre-wrap break-words rounded-lg bg-muted p-4 text-sm">
          {detail.raw_markdown}
        </pre>
      ) : (
        <div className="space-y-5">
          <section>
            <h4 className="font-medium">母题完整原文（含答案）</h4>
            <ExamMarkdown
              content={detail.raw_markdown}
              resources={detail.resources}
            />
          </section>
          {detail.subquestions.length > 0 && (
            <details>
              <summary className="cursor-pointer font-medium">
                按小问查看（{detail.subquestions.length}）
              </summary>
              <div className="mt-3 space-y-4">
                {detail.subquestions.map((part, index) => (
                  <section
                    key={`${part.path.join(".")}-${index}`}
                    className="rounded-lg border p-3"
                  >
                    <h5 className="font-medium">
                      {part.path.join(" / ") || `小问 ${index + 1}`}
                      {part.printed_marks != null &&
                        ` · ${part.printed_marks} 分`}
                      {part.withdrawn && " · 已撤回"}
                    </h5>
                    <ExamMarkdown
                      content={part.raw_markdown}
                      resources={detail.resources}
                    />
                    <p className="mt-2 text-xs">
                      章节：{part.chapters.join("、") || "未知"}；学习目标：
                      {part.learning_outcomes.join("、") || "缺失"}
                    </p>
                  </section>
                ))}
              </div>
            </details>
          )}
        </div>
      )}
      <details>
        <summary className="cursor-pointer">
          镜像来源（{detail.mirrors.length}）
        </summary>
        <ul className="mt-2 space-y-1 break-all text-sm">
          {detail.mirrors.map((mirror, index) => (
            <li key={index}>
              {mirror.source_path} · Q{mirror.question_number} →{" "}
              {mirror.canonical_path}
            </li>
          ))}
        </ul>
      </details>
      <details>
        <summary className="cursor-pointer">Syllabus 与通用评分说明</summary>
        {(
          [
            ["Syllabus", detail.syllabus],
            ["通用评分说明", detail.general_ms],
          ] as const
        ).map(([label, document]) => (
          <section key={label} className="mt-3">
            <h4 className="font-medium">{label}</h4>
            {document ? (
              <>
                <p className="break-all text-xs">
                  {document.path} · {document.sha256}
                </p>
                <ExamMarkdown content={document.raw_markdown} resources={[]} />
              </>
            ) : (
              <p className="text-sm">未提供</p>
            )}
          </section>
        ))}
      </details>
    </>
  );
}
