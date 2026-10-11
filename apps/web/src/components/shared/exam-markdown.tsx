"use client";

import { useEffect, useState } from "react";
import { MarkdownRenderer } from "./markdown-renderer";
import { getBankResource, type BankResource } from "@/lib/api/exam-bank";

function ResourceImage({
  resource,
  alt,
}: {
  resource?: BankResource;
  alt: string;
}) {
  const [url, setUrl] = useState<string>();
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let active = true;
    let objectUrl: string | undefined;
    if (
      resource &&
      [
        "image/png",
        "image/jpeg",
        "image/webp",
        "image/gif",
        "image/bmp",
      ].includes(resource.media_type)
    ) {
      void getBankResource(resource.id)
        .then(({ blob, contentType }) => {
          if (!active) return;
          if (
            contentType.split(";")[0].trim().toLowerCase() !==
            resource.media_type
          ) {
            setFailed(true);
            return;
          }
          objectUrl = URL.createObjectURL(blob);
          setUrl(objectUrl);
        })
        .catch(() => {
          if (active) setFailed(true);
        });
    }
    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [resource]);
  if (
    failed ||
    !resource ||
    ![
      "image/png",
      "image/jpeg",
      "image/webp",
      "image/gif",
      "image/bmp",
    ].includes(resource.media_type)
  )
    return <span role="note">{alt || "图片"}：资源不可用或被阻止。</span>;
  if (!url) return <span role="status">正在加载图片…</span>;
  // Authenticated bytes only; SVG and remote URLs are never used.
  // eslint-disable-next-line @next/next/no-img-element
  return <img src={url} alt={alt} className="h-auto max-w-full" />;
}

export function ExamMarkdown({
  content,
  resources,
}: {
  content: string;
  resources: BankResource[];
}) {
  return (
    <MarkdownRenderer
      content={content}
      examPreview
      className="min-w-0 break-words [&_.katex-display]:overflow-x-auto"
      imageComponent={({ src, alt }) => {
        const reference = typeof src === "string" ? src : "";
        const allowed =
          reference && !/^(?:[a-z][a-z\d+.-]*:|\/\/|\/)/i.test(reference);
        const resource = allowed
          ? resources.find((item) => item.reference === reference)
          : undefined;
        return (
          <ResourceImage
            key={resource?.id ?? reference}
            resource={resource}
            alt={alt ?? ""}
          />
        );
      }}
    />
  );
}
