{pkgs}: {
  deps = [
    pkgs.libev
    pkgs.python312Packages.pytest
    pkgs.postgresql
    pkgs.openssl
  ];
}
