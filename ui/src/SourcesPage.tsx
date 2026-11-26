// The sources page at /sources (see main.tsx): every document the bot can cite, with a link
// to the publisher's copy. The list is ui/src/sources.json, exported from
// sources/manifest.toml by scripts/export_sources.py (a test keeps the two in step).

import {For, onSettled, Show} from "solid-js";

import {isLinkable} from "./api.ts";
import SOURCES from "./sources.json";

const TYPES: Record<string, string> = {
    assessment: "Assessment",
    annual_report: "Annual report",
    data: "Data",
    paper: "Research paper",
    consensus: "Consensus statement",
    method: "Method",
    taxonomy: "Taxonomy",
    energy: "Energy",
};

// The manifest's licence codes in plain words (sources/manifest.toml explains each).
const LICENCES: Record<string, string> = {
    open: "Open",
    "cc-by": "CC BY",
    "non-commercial": "Non-commercial",
    gov: "Government licence",
    restricted: "Short extracts only",
    unverified: "Not stated",
};

const dateFormat = new Intl.DateTimeFormat(undefined, {day: "numeric", month: "short", year: "numeric"});

function captured(iso: string): string {
    const d = new Date(`${iso}T00:00:00Z`);
    return Number.isNaN(d.getTime()) ? iso : dateFormat.format(d);
}

export default function SourcesPage() {
    onSettled(() => {
        document.title = "Climate Chat sources";
        document.body.classList.add("plain");
    });

    return (
        <main class="logs-page sources-page">
            <a class="back" href="/">
                Back to Climate Chat
            </a>
            <header class="logs-head">
                <div>
                    <h1>Sources</h1>
                    <p class="intro">
                        Replies only quote these {SOURCES.length} documents, and every reply cites the ones it
                        used. Each title links to the publisher's own copy. These documents form the knowledge based
                        used by the LLM when replying. My intention is to add much more curated information and examples
                        in the future.
                    </p>
                </div>
            </header>

            <div class="table-scroll">
                <table class="logs source-list">
                    <thead>
                    <tr>
                        <th scope="col" class="num">#</th>
                        <th scope="col">Source</th>
                        <th scope="col">Type</th>
                        <th scope="col" class="num">Year</th>
                        <th scope="col">Reuse terms</th>
                    </tr>
                    </thead>
                    <tbody>
                    <For each={SOURCES}>
                        {(s) => (
                            <tr>
                                <td class="num">{Number(s.id)}</td>
                                <td class="title">
                                    <Show when={isLinkable(s.url)} fallback={s.title}>
                                        <a href={s.url} target="_blank" rel="noopener noreferrer">
                                            {s.title}
                                        </a>
                                    </Show>
                                    <Show when={s.captured}>
                                        {(date) => <span class="captured">Web page captured {captured(date())}</span>}
                                    </Show>
                                </td>
                                <td>{TYPES[s.type] ?? s.type}</td>
                                <td class="num">{s.published}</td>
                                <td>{LICENCES[s.licence] ?? s.licence}</td>
                            </tr>
                        )}
                    </For>
                    </tbody>
                </table>
            </div>
        </main>
    );
}
