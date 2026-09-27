"use client";

export function DeleteConferenceButton({
  conferenceId,
  action,
}: {
  conferenceId: string;
  action: (formData: FormData) => void | Promise<void>;
}) {
  return (
    <form
      action={action}
      onSubmit={(event) => {
        if (!window.confirm("Delete this conference and every paper on it?")) {
          event.preventDefault();
        }
      }}
    >
      <input type="hidden" name="conference_id" value={conferenceId} />
      <button type="submit" className="shrink-0 text-[11px] text-[#8c3a2f]">
        Delete
      </button>
    </form>
  );
}
