import ExplainLayer from "../components/ExplainLayer";
import "./globals.css";

export const metadata = {
  title: {
    default: "FinSight",
    template: "%s · FinSight",
  },
  description: "Portfolio, market, and security intelligence workspace",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>
        <ExplainLayer />
        <div className="shell">{children}</div>
      </body>
    </html>
  );
}
