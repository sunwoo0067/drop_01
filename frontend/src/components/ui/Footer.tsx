import { HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export interface FooterProps extends HTMLAttributes<HTMLDivElement> {
    version?: string;
}

const Footer = ({ className, version = "1.0.0", ...props }: FooterProps) => {
    return (
        <footer
            className={cn(
                "flex items-center justify-between px-4 py-1.5 border-t border-border bg-card text-[10px] text-muted-foreground",
                className
            )}
            {...props}
        >
            <span>&copy; 2025 Drop Automata. All rights reserved.</span>
            <div className="flex items-center gap-3">
                <a href="#" className="hover:text-foreground transition-colors">이용약관</a>
                <a href="#" className="hover:text-foreground transition-colors">개인정보처리방침</a>
                <span>v{version}</span>
            </div>
        </footer>
    );
};

Footer.displayName = "Footer";

export { Footer };
