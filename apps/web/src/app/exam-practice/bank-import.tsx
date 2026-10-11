"use client";

import { useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  uploadExamBank,
  type BankSummary,
  type ImportResult,
} from "@/lib/api/exam-bank";
import { canImportPreflight, preflightIssues } from "@/lib/exam-bank-preflight";
import { BankIssues } from "./bank-detail";

export function BankImport({
  banks,
  onImported,
}: {
  banks: BankSummary[];
  onImported: () => void;
}) {
  const [file, setFile] = useState<File>();
  const [subject, setSubject] = useState("");
  const [source, setSource] = useState("");
  const [name, setName] = useState("");
  const [bankId, setBankId] = useState("");
  const [questionDir, setQuestionDir] = useState("passyear/extracted");
  const [syllabusPath, setSyllabusPath] = useState("reference.md");
  const [generalMsPath, setGeneralMsPath] = useState("");
  const [report, setReport] = useState<Record<string, unknown>>();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const idempotencyKey = useRef<string | undefined>(undefined);
  const reset = () => {
    setReport(undefined);
    setMessage("");
    idempotencyKey.current = undefined;
  };
  const submit = async (action: "preview" | "import") => {
    if (!file) return;
    setBusy(true);
    setMessage("");
    const data = new FormData();
    data.set("file", file);
    data.set("subject", subject);
    data.set("source", source);
    data.set("question_dir", questionDir);
    data.set("syllabus_path", syllabusPath);
    if (generalMsPath) data.set("general_ms_path", generalMsPath);
    if (action === "import") {
      data.set("name", name);
      if (bankId) data.set("bank_id", bankId);
      else {
        idempotencyKey.current ??= crypto.randomUUID();
        data.set("idempotency_key", idempotencyKey.current);
      }
    }
    try {
      const result = await uploadExamBank(action, data);
      if (action === "preview") setReport(result as Record<string, unknown>);
      else {
        const imported = result as ImportResult;
        setMessage(
          imported.reused
            ? "内容完全一致，已复用现有导入（幂等）。"
            : `管理导入完成，版本 ${imported.import_version}。`,
        );
        setReport(undefined);
        idempotencyKey.current = undefined;
        onImported();
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "请求失败，请重试。");
    } finally {
      setBusy(false);
    }
  };
  const fields = [
    ["学科", subject, setSubject],
    ["来源", source, setSource],
    ["题库名称", name, setName],
    ["题文目录", questionDir, setQuestionDir],
    ["Syllabus 路径", syllabusPath, setSyllabusPath],
    ["通用评分说明路径（可选）", generalMsPath, setGeneralMsPath],
  ] as const;
  const issues = preflightIssues(report);
  const canImport = canImportPreflight(report);
  return (
    <details className="rounded-xl border bg-card p-4">
      <summary className="cursor-pointer font-medium">
        ZIP 预检与管理导入
      </summary>
      <p className="my-3 text-sm">
        先预检结构与资源；结构和安全错误会阻止导入，仅缺官方评分内容可作为管理缺口保留。管理导入不会启用正式练习。
      </p>
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="text-sm">
          ZIP 文件
          <input
            type="file"
            accept=".zip"
            className="mt-1 block w-full"
            disabled={busy}
            onChange={(event) => {
              setFile(event.target.files?.[0]);
              reset();
            }}
          />
        </label>
        <label className="text-sm">
          修订已有题库
          <select
            value={bankId}
            disabled={busy}
            className="mt-1 w-full rounded-md border bg-background p-2"
            onChange={(event) => {
              setBankId(event.target.value);
              reset();
            }}
          >
            <option value="">新建题库</option>
            {banks.map((bank) => (
              <option key={bank.id} value={bank.id}>
                {bank.name}
              </option>
            ))}
          </select>
        </label>
        {fields.map(([label, value, setter]) => (
          <label key={label} className="text-sm">
            {label}
            <input
              value={value}
              disabled={busy}
              className="mt-1 w-full rounded-md border bg-background p-2"
              onChange={(event) => {
                setter(event.target.value);
                reset();
              }}
            />
          </label>
        ))}
      </div>
      <div className="mt-4 flex flex-wrap gap-3">
        <Button
          disabled={busy || !file || !subject.trim() || !source.trim()}
          onClick={() => void submit("preview")}
        >
          预检 ZIP
        </Button>
        <Button
          variant="outline"
          disabled={busy || !canImport || !name.trim()}
          onClick={() => void submit("import")}
        >
          确认管理导入
        </Button>
      </div>
      {busy && (
        <p role="status" className="mt-3">
          正在处理 ZIP…
        </p>
      )}
      {message && (
        <p role="status" className="mt-3">
          {message}
        </p>
      )}
      {report && (
        <div className="mt-4 space-y-3">
          <p>
            正本 {String(report.canonical_question_blocks ?? "未知")}
            ；已验证镜像 {String(report.verified_mirrors ?? "未知")}；错误{" "}
            {String(report.error_count ?? "未知")}
          </p>
          <BankIssues issues={issues} />
          <details>
            <summary>完整预检报告</summary>
            <pre className="overflow-auto whitespace-pre-wrap break-words text-xs">
              {JSON.stringify(report, null, 2)}
            </pre>
          </details>
          {!canImport && (
            <p role="alert">预检存在错误或结果不完整，无法导入。</p>
          )}
        </div>
      )}
    </details>
  );
}
