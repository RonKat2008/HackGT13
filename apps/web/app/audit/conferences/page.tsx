import conferenceFixture from "../fixtures/conference.json";
import {
  ConferenceDashboard,
  type Conference,
  type ConferencePaper,
  type ConferenceProbe,
} from "./dashboard";

export default function ConferencePage() {
  const conference = conferenceFixture.conference as Conference;
  const papers = conferenceFixture.papers as ConferencePaper[];
  const probe = conferenceFixture.probe as ConferenceProbe;

  return (
    <main className="mx-auto flex w-full max-w-6xl flex-1 flex-col px-6 py-10">
      <ConferenceDashboard
        conference={conference}
        papers={papers}
        probe={probe}
      />
    </main>
  );
}
