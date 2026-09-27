import Link from "next/link";
import { signOut } from "@/lib/auth";

export function AccountMenu({ email }: { email: string }) {
  return (
    <form action={signOut} className="mt-auto shrink-0 border-t border-[#e4dcd0] pt-3">
      <p className="truncate text-[11px] text-[#6b645c]">{email}</p>
      <Link href="/author" className="mt-2 block text-xs underline decoration-[#c4a15a] underline-offset-4">
        Author desk
      </Link>
      <button className="mt-1 text-xs underline decoration-[#c4a15a] underline-offset-4" type="submit">
        Sign out
      </button>
    </form>
  );
}
