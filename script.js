window.onload = () => {
    $.get('/api/news').then((r) => {
        let html = '', data = [];
        for (let i = 0; i < r.length; i++) {
            html += `
                    <tr data-toggle="collapse" data-target=".order${i}">
                        <td>&gt;</td>
                        <td><a href="${r[i].url}" target="_blank">${r[i].name} (${r[i]['commits'].length})</a></td>
                    </tr>
                `;
            for (let j = 0; j < r[i]['commits'].length; j++) {
                html += `
                        <tr class="collapse order${i}">
                            <td>${j + 1}</td>
                            <td></td>
                            <td><a href="${r[i]['commits'][j].link}" target="_blank">${r[i]['commits'][j].name}</a></td>
                            <td>
                                <span style="color: green">+${r[i]['commits'][j].additions}</span>
                                /
                                <span style="color: red">-${r[i]['commits'][j].deletions}</span>
                            </td>
                            <td>${r[i]['commits'][j].last_modified}</td>
                            <td>
                                <input
                                    class="form-check-input checkbox"
                                    type="checkbox"
                                    id="r${i}-c${j}-chb"
                                    value=""
                                    ${r[i]['commits'][j].viewed ? 'checked' : ''}>
                            </td>
                        </tr>
                    `;
                data[`r${i}-c${j}-chb`] = {repo_id: r[i].id, commit_sha: r[i]['commits'][j].sha};
            }
        }
        $('#tbody-id').html(html);
        $(`.checkbox`).change((e) => {
            $.ajax({
                url: '/api/viewed?' + $.param(data[e.target.id]),
                type: e.target.checked ? 'POST' : 'DELETE',
            }).then((r) => console.log('updated', r));
        });
    })
};