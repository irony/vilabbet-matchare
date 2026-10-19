import type { JobState } from "@/lib/api";
import FlowDetail from "@/screens/FlowDetail";

/** Översiktsvyn: den tematiserade ReactFlow-processkartan (mörk grön bas,
 *  ljusgröna band- och nodkort — presentations-stilen). Mellanstegen i
 *  är borttagna: /app visar vit klassisk sida som standard och knappen
 *  "⤢ översiktsvy" landar direkt här. */
export default function FlowScreen({ title, job }: { title: string; job: JobState }) {
  return <FlowDetail title={title} job={job} />;
}
