import Link from "next/link";

export default function ExamPracticePage() {
  return <div className="mx-auto max-w-3xl space-y-6 px-4 py-10 sm:px-8">
    <Link href="/" className="text-sm underline">返回 OpenTutor</Link>
    <div><h1 className="mt-2 text-3xl font-semibold">自适应刷题工作台</h1></div>
    <section className="rounded-2xl border bg-card p-6"><h2 className="text-lg font-medium">题库尚未接入</h2><p className="mt-2 text-muted-foreground">暂不可选题。后续可按章节浏览题目并安排练习。</p></section>
    <section className="rounded-2xl border bg-card p-6"><h2 className="text-lg font-medium">PDF 练习尚未开放</h2><p className="mt-2 text-muted-foreground">练习 PDF 下载、iPad 手写答案上传与批改尚不可用。</p></section>
  </div>;
}
