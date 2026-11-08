# Contributing

This is a small academic project focused on making the existing CGM analysis reproducible. Contributions that improve reproducibility or clarify the documentation are welcome.

## Reporting problems

Use the [reproducibility issue form](https://github.com/CrisCorreaS/capstone_repo/issues/new?template=reproducibility_problem.yml). Include enough context to repeat the problem, for example: the project revision, your operating system, the command or steps you tried and relevant error output.

## Proposing changes

Keep changes focused, use small descriptive commits and submit a pull request linked to the relevant issue. Prefer a Conventional Commit-style PR title, such as `fix: resolve report paths` or `docs: clarify setup`. Follow the [pull request template](.github/pull_request_template.md) for the description.

For changes affecting execution, run these commands from the repository root:

```
pixi install --locked
pixi run --locked reproduce
```

For documentation-only changes, check wording, links and consistency with the project; a full analysis run is unnecessary. Describe the checks performed and their results, plus any checks not run and why.

Keep generated data, rendered reports and saved notebook outputs out of commits. Explicitly identify and discuss changes affecting scientific calculations.
