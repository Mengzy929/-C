/** Draft view contract only; not a frozen team schema or a React dependency. */
export interface SourceSpan {
  paragraph_id: string;
  /** UTF-16 code-unit offsets for JavaScript String.slice. End is exclusive. */
  start_utf16: number;
  end_utf16: number;
}
export interface ReadingCardProps {
  question: { id: string; stage: number; total: number; title: string; text: string; source: SourceSpan };
  hint: string;
  explanation: string;
  feedback: null | {verdict: "pass" | "off_track" | "empty" | "wrong"; text: string; after_explanation: boolean};
  onAnswer: (answer: string, paragraphId: string | null) => void;
  onHint: () => void;
  onExplainConfirmed: () => void;
  onNext: () => void;
}
