"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { BankImport } from "./bank-import";
import { BankDetail } from "./bank-detail";
import {
  getBankFacets,
  getBankQuestion,
  listBankQuestions,
  listExamBanks,
  type BankSummary,
  type BankFilters,
  type BankFacets,
  type QuestionPage,
  type QuestionDetail,
} from "@/lib/api/exam-bank";

const emptyFacets: BankFacets = {
  subjects: [],
  sources: [],
  years: [],
  chapters: [],
};
export default function ExamPracticePage() {
  const [banks, setBanks] = useState<BankSummary[]>([]);
  const [facets, setFacets] = useState<BankFacets>(emptyFacets);
  const [filters, setFilters] = useState<BankFilters>({});
  const [page, setPage] = useState(1);
  const [result, setResult] = useState<QuestionPage>();
  const [selectedId, setSelectedId] = useState("");
  const [versionId, setVersionId] = useState("");
  const [detail, setDetail] = useState<QuestionDetail>();
  const [error, setError] = useState("");
  const [detailError, setDetailError] = useState("");
  const [detailRequest, setDetailRequest] = useState(0);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let active = true;
    void listExamBanks()
      .then((value) => {
        if (active) setBanks(value);
      })
      .catch(() => {
        if (active) setError("题库加载失败，请重试。");
      });
    return () => {
      active = false;
    };
  }, [revision]);
  useEffect(() => {
    let active = true;
    void getBankFacets(filters.bank_id)
      .then((value) => {
        if (active) setFacets(value);
      })
      .catch(() => {
        if (active) setError("分类加载失败，请重试。");
      });
    return () => {
      active = false;
    };
  }, [filters.bank_id, revision]);
  useEffect(() => {
    let active = true;
    void listBankQuestions(filters, page)
      .then((value) => {
        if (active) setResult(value);
      })
      .catch(() => {
        if (active) setError("题目列表加载失败，请重试。");
      });
    return () => {
      active = false;
    };
  }, [filters, page, revision]);
  useEffect(() => {
    let active = true;
    if (selectedId)
      void getBankQuestion(selectedId, versionId || undefined)
        .then((value) => {
          if (active) setDetail(value);
        })
        .catch(() => {
          if (active) setDetailError("详情加载失败，请重新选择题目或版本。");
        });
    return () => {
      active = false;
    };
  }, [selectedId, versionId, detailRequest]);
  const resetView = () => {
    setError("");
    setResult(undefined);
    setSelectedId("");
    setVersionId("");
    setDetail(undefined);
    setDetailError("");
  };
  const filter = (key: keyof BankFilters, value: string) => {
    resetView();
    if (key === "bank_id") setFacets(emptyFacets);
    setPage(1);
    setFilters(
      key === "bank_id" ? { bank_id: value } : { ...filters, [key]: value },
    );
  };
  return (
    <div className="mx-auto max-w-7xl space-y-5 px-4 py-6 sm:px-8">
      <Link href="/" className="text-sm underline">
        返回 OpenTutor
      </Link>
      <h1 className="text-3xl font-semibold">题库管理浏览</h1>
      <p
        role="note"
        className="rounded-xl border border-amber-500/50 bg-amber-500/10 p-4 text-sm"
      >
        题库管理预览：含答案，内容尚未验收；用途未分配，不可用于正式练习，不记录学习进度。
      </p>
      <BankImport
        banks={banks}
        onImported={() => {
          resetView();
          setPage(1);
          setRevision((value) => value + 1);
        }}
      />
      <section
        aria-label="题库筛选"
        className="grid gap-3 rounded-xl border p-4 sm:grid-cols-2 lg:grid-cols-5"
      >
        <label className="text-sm">
          题库
          <select
            value={filters.bank_id ?? ""}
            onChange={(event) => filter("bank_id", event.target.value)}
            className="mt-1 w-full rounded-md border bg-background p-2"
          >
            <option value="">全部</option>
            {banks.map((bank) => (
              <option key={bank.id} value={bank.id}>
                {bank.name}
              </option>
            ))}
          </select>
        </label>
        {(
          [
            ["学科", "subject", facets.subjects],
            ["来源", "source", facets.sources],
            ["年份", "year", facets.years],
            ["章节", "chapter", facets.chapters],
          ] as const
        ).map(([label, key, values]) => (
          <label key={key} className="text-sm">
            {label}
            <select
              value={filters[key] ?? ""}
              onChange={(event) => filter(key, event.target.value)}
              className="mt-1 w-full rounded-md border bg-background p-2"
            >
              <option value="">全部</option>
              {values.map((value) => (
                <option key={value.value} value={value.value}>
                  {value.label}（{value.count}）
                </option>
              ))}
            </select>
          </label>
        ))}
        <Button
          variant="ghost"
          onClick={() => {
            resetView();
            setFilters({});
            setPage(1);
          }}
        >
          清除筛选
        </Button>
      </section>
      {error && (
        <div role="alert">
          {error}
          <Button
            variant="link"
            onClick={() => {
              resetView();
              setRevision((value) => value + 1);
            }}
          >
            重试
          </Button>
        </div>
      )}
      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
        <section aria-label="题目列表" className="min-w-0 space-y-3">
          {!result && !error && <p role="status">正在加载题目…</p>}
          {result && (
            <>
              <p className="text-sm">
                共 {result.total} 道母题 · 第 {result.page} 页
              </p>
              {result.items.length === 0 && (
                <p className="rounded-xl border p-5">
                  暂无匹配题目，请调整筛选或导入题库。
                </p>
              )}
              {result.items.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  aria-pressed={selectedId === item.id}
                  className="w-full rounded-xl border bg-card p-4 text-left hover:bg-muted focus-visible:ring-2"
                  onClick={() => {
                    setDetail(undefined);
                    setDetailError("");
                    setSelectedId(item.id);
                    setVersionId("");
                    setDetailRequest((value) => value + 1);
                  }}
                >
                  <span className="block font-medium">{item.label}</span>
                  <span className="mt-1 block break-words text-sm text-muted-foreground">
                    {item.subject} · {item.source} · {item.year ?? "年份未知"} ·
                    版本 {item.version_number}
                    <br />
                    {item.chapters.join("、") || "章节未知"}
                  </span>
                  <span className="mt-2 block text-xs">
                    {item.issues.length} 项缺口 / 提示 · 未分配 · 不可练习
                  </span>
                </button>
              ))}
              <div className="flex items-center justify-between gap-3">
                <Button
                  variant="outline"
                  disabled={page <= 1}
                  onClick={() => {
                    resetView();
                    setPage(page - 1);
                  }}
                >
                  上一页
                </Button>
                <Button
                  variant="outline"
                  disabled={page * result.page_size >= result.total}
                  onClick={() => {
                    resetView();
                    setPage(page + 1);
                  }}
                >
                  下一页
                </Button>
              </div>
            </>
          )}
        </section>
        <section
          aria-label="题目详情"
          className="min-w-0 space-y-4 rounded-xl border bg-card p-4 sm:p-6"
        >
          {!selectedId && (
            <p className="text-muted-foreground">
              选择一道母题查看完整上下文、来源、版本与缺口。
            </p>
          )}
          {selectedId && !detail && !detailError && (
            <p role="status">正在加载详情…</p>
          )}
          {detailError && (
            <div role="alert">
              {detailError}
              <Button
                variant="link"
                onClick={() => {
                  setDetailError("");
                  setDetailRequest((value) => value + 1);
                }}
              >
                重试详情
              </Button>
            </div>
          )}
          {detail && (
            <>
              <label className="block text-sm">
                版本历史
                <select
                  aria-label="版本历史"
                  className="ml-2 max-w-full rounded-md border bg-background p-2"
                  value={versionId}
                  onChange={(event) => {
                    setDetail(undefined);
                    setDetailError("");
                    setVersionId(event.target.value);
                  }}
                >
                  <option value="">当前版本</option>
                  {detail.versions.map((version) => (
                    <option key={version.id} value={version.id}>
                      版本 {version.version_number} ·{" "}
                      {new Date(version.created_at).toLocaleString()}
                    </option>
                  ))}
                </select>
              </label>
              <BankDetail key={detail.version_id} detail={detail} />
            </>
          )}
        </section>
      </div>
      <p className="text-sm text-muted-foreground">
        PDF 练习、手写上传与批改尚未开放。
      </p>
    </div>
  );
}
