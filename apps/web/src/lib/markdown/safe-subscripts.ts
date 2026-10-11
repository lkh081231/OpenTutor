interface MarkdownNode {
  type: string;
  value?: string;
  children?: MarkdownNode[];
  data?: { hName: string };
}

/** Convert only exact, attribute-free sub/sup pairs. No arbitrary HTML parser. */
export function remarkSafeSubscripts() {
  return (tree: MarkdownNode) => {
    const visit = (node: MarkdownNode) => {
      if (!node.children) return;
      const children = node.children;
      for (let index = 0; index < children.length; index++) {
        const opening = children[index];
        const match =
          opening.type === "html"
            ? /^<(sup|sub)>$/i.exec(opening.value ?? "")
            : null;
        if (!match) {
          visit(opening);
          continue;
        }
        const tag = match[1].toLowerCase();
        const closing = children.findIndex(
          (candidate, position) =>
            position > index &&
            candidate.type === "html" &&
            candidate.value?.toLowerCase() === `</${tag}>`,
        );
        if (closing < 0) continue;
        const content = children.slice(index + 1, closing);
        if (content.some((candidate) => candidate.type === "html")) continue;
        children.splice(index, closing - index + 1, {
          type: "safeSubscript",
          data: { hName: tag },
          children: content,
        });
      }
    };
    visit(tree);
  };
}
