import { ACTION_LABEL, absoluteTime, actionTone, describeEvent, timeAgo } from "@/lib/format";
import type { AuditEvent } from "@/lib/types";
import Link from "next/link";
import { EnvTag } from "./flag-parts";
import { Badge } from "./ui/feedback";

export function AuditRow({ event, showFlag = true }: { event: AuditEvent; showFlag?: boolean }) {
  const summary = describeEvent(event);
  return (
    <li className="flex flex-wrap items-start gap-x-3 gap-y-1 px-5 py-3" data-testid="audit-row">
      <Badge tone={actionTone(event.action)} className="shrink-0">
        {ACTION_LABEL[event.action] ?? event.action}
      </Badge>
      <div className="min-w-0 flex-1 basis-60">
        <p className="flex flex-wrap items-center gap-2 text-[13.5px]">
          {showFlag && event.flag_key && (
            <Link href={`/flags/${event.flag_key}`} className="font-mono text-[13px] font-medium hover:underline">
              {event.flag_key}
            </Link>
          )}
          {event.environment && <EnvTag env={event.environment} />}
          {summary && <span className="text-muted">{summary}</span>}
        </p>
        <p className="mt-0.5 text-xs text-subtle">by {event.actor}</p>
      </div>
      <time dateTime={event.created_at} title={absoluteTime(event.created_at)} className="shrink-0 text-xs text-muted">
        {timeAgo(event.created_at)}
      </time>
    </li>
  );
}
