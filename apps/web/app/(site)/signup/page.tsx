import { AuthForm } from "../auth-form";

export default async function SignupPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string; sent?: string }>;
}) {
  const params = await searchParams;
  return <AuthForm mode="signup" error={params.error} sent={Boolean(params.sent)} />;
}
