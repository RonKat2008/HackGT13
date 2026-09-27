import { AccountSplit, type DeskChoice } from "../split";

export default async function SignupPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string; sent?: string; desk?: string }>;
}) {
  const params = await searchParams;
  const desk: DeskChoice | undefined =
    params.desk === "author" || params.desk === "conference" ? params.desk : undefined;
  return <AccountSplit initial={desk} error={params.error} sent={params.sent === "1"} />;
}
