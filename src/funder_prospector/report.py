PP = "https://projects.propublica.org/nonprofits/organizations"


def render(prospects, applicant):
    lines = [
        f"# Funder prospects for {applicant.name}",
        f"_{applicant.ntee} · {applicant.city}, {applicant.state}_",
        "",
        f"{len(prospects)} funders gave to organizations like this one.",
        "",
    ]
    for p in prospects:
        lines.append(f"## {p.funder_name} ({p.funder_type}, EIN {p.funder_ein})")
        lines.append(f"- funded **{p.n_peers}** peer org(s); total **${p.total_amount:,}**; "
                     f"most recent tax year {p.recent_year or 'n/a'}")
        if p.purposes:
            lines.append(f"- purposes: {'; '.join(p.purposes)}")
        lines.append(f"- {PP}/{p.funder_ein}")
        lines.append("")
    return "\n".join(lines)
