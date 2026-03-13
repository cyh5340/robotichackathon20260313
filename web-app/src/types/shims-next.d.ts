declare module "next" {
  export interface Metadata {
    title?: string;
    description?: string;
  }
}

declare module "next/link" {
  import * as React from "react";

  export interface LinkProps {
    href: string;
    children?: React.ReactNode;
    className?: string;
  }

  export default function Link(props: LinkProps): React.ReactElement;
}

declare namespace JSX {
  interface IntrinsicElements {
    [elemName: string]: any;
  }
}
