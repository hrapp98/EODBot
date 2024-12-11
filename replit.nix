{pkgs}: {
  deps = [
    pkgs.python312Packages.pytest
    pkgs.postgresql
    pkgs.openssl
  ];
}
