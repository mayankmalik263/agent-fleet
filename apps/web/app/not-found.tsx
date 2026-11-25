import Link from "next/link";

export default function NotFound() {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-2 px-6 py-16 text-center">
      <p className="text-[14px] font-semibold">Page not found</p>
      <Link href="/" className="af-btn">
        Back to the dashboard
      </Link>
    </div>
  );
}
