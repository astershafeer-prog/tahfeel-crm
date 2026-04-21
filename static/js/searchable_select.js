// Searchable select — pure JS, no library needed
function makeSearchable(selectId, placeholder) {
  const select = document.getElementById(selectId);
  if (!select) return;

  // Create wrapper
  const wrapper = document.createElement('div');
  wrapper.style.cssText = 'position:relative;';
  select.parentNode.insertBefore(wrapper, select);
  wrapper.appendChild(select);
  select.style.display = 'none';

  // Create search input
  const input = document.createElement('input');
  input.type = 'text';
  input.placeholder = placeholder || 'Type to search...';
  input.style.cssText = 'width:100%;box-sizing:border-box;';
  input.autocomplete = 'off';
  wrapper.insertBefore(input, select);

  // Create dropdown list
  const list = document.createElement('div');
  list.style.cssText = 'position:absolute;top:100%;left:0;right:0;background:var(--bg-card,white);border:1.5px solid var(--border);border-top:none;border-radius:0 0 var(--radius-sm) var(--radius-sm);max-height:220px;overflow-y:auto;z-index:999;display:none;box-shadow:0 4px 12px rgba(0,0,0,0.1);';
  wrapper.appendChild(list);

  // Get options
  const options = Array.from(select.options);
  let selected = select.value;

  function renderList(filter) {
    list.innerHTML = '';
    const filtered = options.filter(o => o.value === '' || o.text.toLowerCase().includes(filter.toLowerCase()));
    filtered.forEach(opt => {
      const item = document.createElement('div');
      item.textContent = opt.text;
      item.style.cssText = `padding:8px 12px;cursor:pointer;font-size:13px;${opt.value === selected ? 'background:var(--info-bg);color:var(--primary);font-weight:600;' : ''}`;
      item.onmouseenter = () => item.style.background = 'var(--info-bg)';
      item.onmouseleave = () => item.style.background = opt.value === selected ? 'var(--info-bg)' : '';
      item.onclick = () => {
        selected = opt.value;
        select.value = opt.value;
        input.value = opt.value ? opt.text : '';
        list.style.display = 'none';
        // Trigger change for due date auto-fill
        select.dispatchEvent(new Event('change'));
      };
      list.appendChild(item);
    });
    list.style.display = filtered.length ? 'block' : 'none';
  }

  // Set initial display value
  if (select.value) {
    const cur = options.find(o => o.value === select.value);
    if (cur) input.value = cur.text;
  }

  input.onfocus = () => renderList(input.value);
  input.oninput = () => { selected = ''; select.value = ''; renderList(input.value); };
  document.addEventListener('click', e => { if (!wrapper.contains(e.target)) list.style.display = 'none'; });
}
