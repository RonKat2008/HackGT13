import { AuthForm } from "../auth-form";

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string; next?: string }>;
}) {
  const params = await searchParams;
  return <AuthForm mode="login" error={params.error} next={params.next} />;
}
