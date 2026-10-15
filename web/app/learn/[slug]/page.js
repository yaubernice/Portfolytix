import { Suspense } from "react";
import LearnArticle from "./article";

export default function LearnTermPage() {
  return (
    <Suspense fallback={null}>
      <LearnArticle />
    </Suspense>
  );
}
