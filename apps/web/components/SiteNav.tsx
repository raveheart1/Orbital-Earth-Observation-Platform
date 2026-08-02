"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const GITHUB_URL = "https://github.com/raveheart1/Orbital-Earth-Observation-Platform";

const LINKS: { href: string; label: string; exact: boolean }[] = [
  { href: "/", label: "Home", exact: true },
  { href: "/analyses/new", label: "New analysis", exact: true },
  { href: "/analyses", label: "Analyses", exact: true },
];

export default function SiteNav() {
  const pathname = usePathname();
  return (
    <nav className="site-nav" aria-label="Primary">
      <ul>
        {LINKS.map((link) => {
          const current = link.exact
            ? pathname === link.href
            : pathname.startsWith(link.href);
          return (
            <li key={link.href}>
              <Link
                href={link.href}
                aria-current={current ? "page" : undefined}
              >
                {link.label}
              </Link>
            </li>
          );
        })}
        <li>
          <a href={GITHUB_URL} target="_blank" rel="noopener noreferrer">
            GitHub
          </a>
        </li>
      </ul>
    </nav>
  );
}
