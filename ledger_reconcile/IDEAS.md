Ideas of things to fix. Always use TDD! Always use data-driven tests with HTML previews! Always run `mise run check` before committing! Actually check off here in the commit! Commit each separately.

- [x] I want a button to reverse the sort order.
- [x] Needs to have a "refresh from file" button. Which should be "r" and the current "r" should be "c".
- [x] The table needs a check code column.
- [x] I think there's an awkward amount of manually updating labels in the UI. Can you use Textual's reactive capabilities instead?
- [x] Is the filtering to filtered_transactions still necessary? Or the checking against accounts afterwards? I think the API now just gives us the right thing, no?
- [x] action_toggle_status does a weird thing where it maps through the transaction and matches based on account name (which isn't unique). Why not have the row key just be the posting line number?
- [x] I don't think the file watcher detects when I save the file in VSCode. Maybe it's not detecting atomic rewrites?
